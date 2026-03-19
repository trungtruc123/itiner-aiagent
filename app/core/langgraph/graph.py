import json
from typing import Any, Dict, Literal, Optional

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.core.config import settings
from app.core.langgraph.state import TravelAgentState
from app.core.langgraph.tools.activities import recommend_activities
from app.core.langgraph.tools.destination import get_destination_details, recommend_destinations
from app.core.langgraph.tools.flight import book_flight, search_flights
from app.core.langgraph.tools.hotel import confirm_hotel_booking, prepare_hotel_booking, search_hotels
from app.core.langgraph.tools.weather import get_weather
from app.core.metrics import AGENT_STEP_COUNT
from app.core.prompts.system import TRAVEL_AGENT_SYSTEM_PROMPT
from app.core.rag.retriever import query_hotel_policies
from app.services.llm import get_langfuse_handler
from app.services.memory import add_memory, search_memory

logger = structlog.get_logger(__name__)

ALL_TOOLS = [
    search_flights,
    book_flight,
    search_hotels,
    prepare_hotel_booking,
    confirm_hotel_booking,
    recommend_destinations,
    get_destination_details,
    get_weather,
    recommend_activities,
    query_hotel_policies,
]

TOOL_NODE = ToolNode(ALL_TOOLS)


async def agent_node(state: TravelAgentState) -> Dict[str, Any]:
    """Main agent node that processes messages and decides next action."""
    AGENT_STEP_COUNT.labels(step_name="agent_node", status="started").inc()

    logger.info(
        "agent_node_processing",
        user_id=state.user_id,
        session_id=state.session_id,
        message_count=len(state.messages),
    )

    system_prompt = TRAVEL_AGENT_SYSTEM_PROMPT.format(
        memory_context=state.memory_context or "No previous context available.",
    )

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        api_key=settings.OPENAI_API_KEY,
        streaming=True,
    )
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    langfuse_handler = get_langfuse_handler(
        session_id=state.session_id,
        user_id=state.user_id,
        trace_name="travel_agent",
    )

    messages = [SystemMessage(content=system_prompt)] + list(state.messages)

    # Log all input messages to LLM
    logger.info(
        "llm_input_messages",
        session_id=state.session_id,
        user_id=state.user_id,
        message_count=len(messages),
        messages=[
            {"role": type(msg).__name__, "content": msg.content[:500]}
            for msg in messages
        ],
    )

    response = await llm_with_tools.ainvoke(
        messages,
        config={"callbacks": [langfuse_handler]},
    )

    # Log LLM output message
    logger.info(
        "llm_output_message",
        session_id=state.session_id,
        user_id=state.user_id,
        role=type(response).__name__,
        content=response.content[:500] if response.content else "",
        tool_calls=[
            {"name": tc["name"], "args": tc["args"]}
            for tc in (response.tool_calls or [])
        ],
    )

    AGENT_STEP_COUNT.labels(step_name="agent_node", status="completed").inc()

    return {"messages": [response]}


async def tool_executor_node(state: TravelAgentState) -> Dict[str, Any]:
    """Execute tool calls from the agent."""
    AGENT_STEP_COUNT.labels(step_name="tool_executor", status="started").inc()

    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": []}

    results = await TOOL_NODE.ainvoke({"messages": list(state.messages)})

    AGENT_STEP_COUNT.labels(step_name="tool_executor", status="completed").inc()

    return {"messages": results["messages"]}


async def check_booking_node(state: TravelAgentState) -> Dict[str, Any]:
    """Check if tool results contain a pending hotel booking requiring confirmation."""
    AGENT_STEP_COUNT.labels(step_name="check_booking", status="started").inc()

    for message in reversed(state.messages):
        if not isinstance(message, ToolMessage):
            continue
        try:
            content = json.loads(message.content)
            if content.get("requires_confirmation"):
                logger.info(
                    "hotel_booking_requires_confirmation",
                    booking_id=content.get("booking_id"),
                )
                AGENT_STEP_COUNT.labels(step_name="check_booking", status="completed").inc()
                return {
                    "pending_booking": content,
                    "requires_human_confirmation": True,
                    "current_step": "awaiting_confirmation",
                }
        except (json.JSONDecodeError, TypeError):
            continue

    AGENT_STEP_COUNT.labels(step_name="check_booking", status="completed").inc()
    return {"requires_human_confirmation": False}


async def human_confirmation_node(state: TravelAgentState) -> Dict[str, Any]:
    """Handle human-in-the-loop confirmation for hotel booking.

    This node interrupts the graph and waits for user input.
    The graph resumes when the user provides confirmation.
    """
    AGENT_STEP_COUNT.labels(step_name="human_confirmation", status="started").inc()

    if not state.pending_booking:
        return {"requires_human_confirmation": False, "current_step": "agent"}

    booking = state.pending_booking
    confirmation_message = (
        f"🏨 **Hotel Booking Confirmation Required**\n\n"
        f"**Hotel:** {booking.get('hotel_name', 'N/A')}\n"
        f"**Check-in:** {booking.get('check_in_date', 'N/A')}\n"
        f"**Check-out:** {booking.get('check_out_date', 'N/A')}\n"
        f"**Room:** {booking.get('room_type', 'N/A')}\n"
        f"**Nights:** {booking.get('num_nights', 'N/A')}\n"
        f"**Total Price:** ${booking.get('total_price', 0):.2f} {booking.get('currency', 'USD')}\n\n"
        f"Please reply **'confirm'** to proceed or **'cancel'** to cancel this booking."
    )

    AGENT_STEP_COUNT.labels(step_name="human_confirmation", status="completed").inc()

    return {
        "messages": [AIMessage(content=confirmation_message)],
        "current_step": "awaiting_confirmation",
    }


async def process_confirmation_node(state: TravelAgentState) -> Dict[str, Any]:
    """Process the user's booking confirmation response."""
    AGENT_STEP_COUNT.labels(step_name="process_confirmation", status="started").inc()

    last_human_message = None
    for message in reversed(state.messages):
        if isinstance(message, HumanMessage):
            last_human_message = message
            break

    if not last_human_message:
        return {"current_step": "agent", "requires_human_confirmation": False}

    user_response = last_human_message.content.strip().lower()
    is_confirmed = user_response in ["confirm", "yes", "y", "ok", "proceed", "book"]

    if is_confirmed and state.pending_booking:
        booking_id = state.pending_booking.get("booking_id", "")
        confirmation_result = await confirm_hotel_booking.ainvoke({"booking_id": booking_id})

        await add_memory(
            user_id=state.user_id,
            content=f"User booked hotel: {state.pending_booking.get('hotel_name')} "
                    f"from {state.pending_booking.get('check_in_date')} "
                    f"to {state.pending_booking.get('check_out_date')}",
            metadata={"type": "hotel_booking", "booking_id": booking_id},
        )

        result_msg = AIMessage(
            content=f"Your hotel booking has been confirmed! {confirmation_result}\n\n"
                    "Is there anything else you'd like help with for your trip?"
        )
    else:
        result_msg = AIMessage(
            content="The hotel booking has been cancelled. "
                    "Would you like me to search for other hotels or help with something else?"
        )

    AGENT_STEP_COUNT.labels(step_name="process_confirmation", status="completed").inc()

    return {
        "messages": [result_msg],
        "pending_booking": None,
        "booking_confirmed": is_confirmed,
        "requires_human_confirmation": False,
        "current_step": "agent",
    }


async def memory_node(state: TravelAgentState) -> Dict[str, Any]:
    """Load user memory context at the start of conversation."""
    AGENT_STEP_COUNT.labels(step_name="memory_node", status="started").inc()

    if not state.user_id:
        return {}

    last_message = ""
    for message in reversed(state.messages):
        if isinstance(message, HumanMessage):
            last_message = message.content
            break

    memories = await search_memory(
        user_id=state.user_id,
        query=last_message or "travel preferences",
        limit=5,
    )

    memory_context = ""
    if memories:
        memory_parts = []
        for mem in memories:
            if isinstance(mem, dict):
                memory_parts.append(mem.get("memory", str(mem)))
            else:
                memory_parts.append(str(mem))
        memory_context = "User's travel history and preferences:\n" + "\n".join(
            f"- {m}" for m in memory_parts
        )

    AGENT_STEP_COUNT.labels(step_name="memory_node", status="completed").inc()

    return {"memory_context": memory_context}


async def save_memory_node(state: TravelAgentState) -> Dict[str, Any]:
    """Save important information from the conversation to long-term memory."""
    AGENT_STEP_COUNT.labels(step_name="save_memory", status="started").inc()

    if not state.user_id:
        return {}

    last_human = None
    last_ai = None
    for message in reversed(state.messages):
        if isinstance(message, HumanMessage) and not last_human:
            last_human = message.content
        if isinstance(message, AIMessage) and not last_ai:
            last_ai = message.content
        if last_human and last_ai:
            break

    if last_human:
        await add_memory(
            user_id=state.user_id,
            content=f"User asked: {last_human}",
            metadata={"type": "conversation", "session_id": state.session_id},
        )

    AGENT_STEP_COUNT.labels(step_name="save_memory", status="completed").inc()
    return {}


def should_continue(state: TravelAgentState) -> Literal["tools", "check_booking", "end"]:
    """Determine the next step after the agent node."""
    last_message = state.messages[-1] if state.messages else None

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "end"


def after_tools(state: TravelAgentState) -> Literal["check_booking"]:
    """Always check for pending bookings after tool execution."""
    return "check_booking"


def after_booking_check(
    state: TravelAgentState,
) -> Literal["human_confirmation", "agent"]:
    """Route based on whether booking confirmation is needed."""
    if state.requires_human_confirmation:
        return "human_confirmation"
    return "agent"


def after_human_input(
    state: TravelAgentState,
) -> Literal["process_confirmation", "agent"]:
    """Route based on whether we're processing a confirmation."""
    if state.requires_human_confirmation and state.pending_booking:
        return "process_confirmation"
    return "agent"


def build_travel_agent_graph() -> StateGraph:
    """Build the LangGraph workflow for the travel planning agent."""
    workflow = StateGraph(TravelAgentState)

    workflow.add_node("memory", memory_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_executor_node)
    workflow.add_node("check_booking", check_booking_node)
    workflow.add_node("human_confirmation", human_confirmation_node)
    workflow.add_node("process_confirmation", process_confirmation_node)
    workflow.add_node("save_memory", save_memory_node)

    workflow.set_entry_point("memory")

    workflow.add_edge("memory", "agent")

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": "save_memory",
        },
    )

    workflow.add_edge("tools", "check_booking")

    workflow.add_conditional_edges(
        "check_booking",
        after_booking_check,
        {
            "human_confirmation": "human_confirmation",
            "agent": "agent",
        },
    )

    # Human confirmation interrupts the graph — the graph will be
    # resumed with a new HumanMessage when the user responds
    workflow.add_edge("human_confirmation", END)

    workflow.add_edge("process_confirmation", "save_memory")

    workflow.add_edge("save_memory", END)

    return workflow


async def create_compiled_graph(
    checkpointer: Optional[AsyncPostgresSaver] = None,
) -> Any:
    """Create and compile the travel agent graph with optional checkpointing."""
    workflow = build_travel_agent_graph()

    compile_kwargs = {}
    if checkpointer:
        compile_kwargs["checkpointer"] = checkpointer

    # Interrupt before human confirmation to allow user input
    compile_kwargs["interrupt_before"] = ["process_confirmation"]

    compiled = workflow.compile(**compile_kwargs)

    logger.info("travel_agent_graph_compiled")
    return compiled
