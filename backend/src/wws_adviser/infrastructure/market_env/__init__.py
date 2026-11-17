"""市场环境适配器（ADR-0014）：直连（腾讯/新浪/东财）与 stub 实现 + 选源工厂。

构造仅在 main.py lifespan 与 reports 执行器（沿 _run_data_maintenance 就地构造先例，
1_REPO §5 注），service 经端口注入不感知具体实现。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wws_adviser.core.config import Settings
    from wws_adviser.ports.market_env import (
        IndexBarProvider,
        IndexQuoteProvider,
        SectorFlowProvider,
    )


def build_market_env_providers(
    settings: "Settings",
) -> "tuple[IndexQuoteProvider, IndexBarProvider, SectorFlowProvider]":
    """按配置选源 → (IndexQuoteProvider, IndexBarProvider, SectorFlowProvider)。"""
    import logging

    logger = logging.getLogger(__name__)
    if settings.market_env_index_source == "direct":
        from wws_adviser.infrastructure.market_env.direct_index_quote import (
            DirectIndexQuoteProvider,
        )
        from wws_adviser.infrastructure.market_env.eastmoney_index_bar import (
            EastmoneyIndexBarProvider,
        )

        logger.info("市场环境指数源：direct（腾讯主源+新浪兜底 / 东财日K+腾讯兜底）")
        quote_provider: IndexQuoteProvider = DirectIndexQuoteProvider(env=settings.env)
        bar_provider: IndexBarProvider = EastmoneyIndexBarProvider(env=settings.env)
    else:
        from wws_adviser.infrastructure.market_env.stub_market_env import (
            StubIndexBarProvider,
            StubIndexQuoteProvider,
        )

        quote_provider = StubIndexQuoteProvider(env=settings.env)
        bar_provider = StubIndexBarProvider(env=settings.env)
    if settings.market_env_sector_source == "direct":
        from wws_adviser.infrastructure.market_env.eastmoney_sector_flow import (
            EastmoneySectorFlowProvider,
        )

        logger.info("市场环境板块资金流源：direct（东财 clist，多域名轮换）")
        sector_provider: SectorFlowProvider = EastmoneySectorFlowProvider(env=settings.env)
    else:
        from wws_adviser.infrastructure.market_env.stub_market_env import (
            StubSectorFlowProvider,
        )

        sector_provider = StubSectorFlowProvider(env=settings.env)
    return quote_provider, bar_provider, sector_provider
