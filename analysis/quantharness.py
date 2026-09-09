"""Optional call into QuantHarness's four-agent TradingGraph (needs a vision LLM key)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

QUANT_HARNESS_ROOT = Path(__file__).resolve().parents[1] / "third_party" / "QuantHarness"

LLM_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DASHSCOPE_API_KEY",
    "MINIMAX_API_KEY",
    "GOOGLE_API_KEY",
)


def llm_provider() -> str | None:
    """Return the first configured QuantHarness LLM provider, if any."""
    mapping = (
        ("OPENAI_API_KEY", "openai"),
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("DASHSCOPE_API_KEY", "qwen"),
        ("MINIMAX_API_KEY", "minimax"),
        ("GOOGLE_API_KEY", "gemini"),
    )
    for env_name, provider in mapping:
        value = os.environ.get(env_name, "").strip()
        if not value or value in {"sk-", "your-openai-api-key-here"}:
            continue
        return provider
    return None


def run_trading_graph(
    kline_data: dict[str, list[Any]],
    symbol: str,
    time_frame: str,
) -> dict[str, Any]:
    """Invoke QuantHarness TradingGraph. Raises if no vision-capable LLM key is set."""
    provider = llm_provider()
    if provider is None:
        raise RuntimeError(
            "QuantHarness's four-agent graph needs a vision LLM key. Set one of: "
            + ", ".join(LLM_ENV_KEYS)
        )

    if str(QUANT_HARNESS_ROOT) not in sys.path:
        sys.path.insert(0, str(QUANT_HARNESS_ROOT))

    from default_config import DEFAULT_CONFIG
    from static_util import generate_kline_image, generate_trend_image
    from trading_graph import TradingGraph

    config = DEFAULT_CONFIG.copy()
    config["agent_llm_provider"] = provider
    config["graph_llm_provider"] = provider
    if provider == "anthropic":
        config["agent_llm_model"] = "claude-haiku-4-5-20251001"
        config["graph_llm_model"] = "claude-haiku-4-5-20251001"
    elif provider == "qwen":
        config["agent_llm_model"] = "qwen3-max"
        config["graph_llm_model"] = "qwen3-vl-plus"
    elif provider == "minimax":
        config["agent_llm_model"] = "MiniMax-M3"
        config["graph_llm_model"] = "MiniMax-M3"
    elif provider == "gemini":
        config["agent_llm_model"] = "gemini-2.5-flash"
        config["graph_llm_model"] = "gemini-2.5-flash"

    graph = TradingGraph(config=config)
    pattern = generate_kline_image(kline_data)
    trend = generate_trend_image(kline_data)
    initial_state = {
        "kline_data": kline_data,
        "analysis_results": None,
        "messages": [],
        "time_frame": time_frame,
        "stock_name": symbol,
        "pattern_image": pattern["pattern_image"],
        "trend_image": trend["trend_image"],
    }
    final_state = graph.graph.invoke(initial_state)
    return {
        "final_trade_decision": final_state.get("final_trade_decision"),
        "indicator_report": final_state.get("indicator_report"),
        "pattern_report": final_state.get("pattern_report"),
        "trend_report": final_state.get("trend_report"),
        "provider": provider,
    }
