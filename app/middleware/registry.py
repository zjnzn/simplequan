from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class RiskLoader:
    """从模块路径或文件路径动态加载风控中间件，组装 RiskPipeline。"""

    def load_module(self, dotted_path: str,
                    params: dict[str, Any] | None = None) -> RiskMiddleware:
        """从 Python 模块路径加载并实例化风控中间件。

        dotted_path: "src.risk.daily_loss.DailyLossMiddleware"
        params: 传给构造函数的关键字参数
        """
        module_path, cls_name = dotted_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            raise ImportError(f"无法导入模块 '{module_path}': {e}") from e

        cls = getattr(module, cls_name, None)
        if cls is None:
            raise AttributeError(f"模块 '{module_path}' 中找不到类 '{cls_name}'")

        mw = cls(**(params or {}))
        log.info("加载风控中间件: %s", mw.name)
        return mw

    def load_file(self, spec: str,
                  params: dict[str, Any] | None = None) -> RiskMiddleware:
        """从文件路径加载风控中间件。

        spec: "/path/to/middleware.py::ClassName"
        """
        if "::" not in spec:
            raise ValueError(f"格式错误，需要 'path.py::ClassName'，得到: {spec}")

        file_path, cls_name = spec.split("::", 1)
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"风控中间件文件不存在: {file_path}")

        spec_obj = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec_obj)
        spec_obj.loader.exec_module(module)

        cls = getattr(module, cls_name, None)
        if cls is None:
            raise AttributeError(f"文件 '{file_path}' 中找不到类 '{cls_name}'")

        mw = cls(**(params or {}))
        log.info("加载风控中间件: %s", mw.name)
        return mw

    def load_all(self, configs: list[dict[str, Any]]) -> RiskPipeline:
        """从配置列表加载中间件并返回组装好的 RiskPipeline。"""
        middlewares: list[RiskMiddleware] = []
        for cfg in configs:
            params = cfg.get("params", {})
            if "module" in cfg:
                middlewares.append(self.load_module(cfg["module"], params))
            elif "file" in cfg:
                middlewares.append(self.load_file(cfg["file"], params))
            else:
                raise ValueError(f"无效风控配置（需要 'module' 或 'file'）: {cfg}")
        return RiskPipeline(middlewares)

def build_default_pre_pipeline() -> RiskPipeline:
    """构建默认 Pre 风控管道（与原 RiskPreCheckHandler 行为一致）。"""
    return RiskPipeline([
        DailyLossMiddleware(),
        DrawdownMiddleware(),
        GlobalLossMiddleware(),
    ])


def build_default_post_pipeline() -> RiskPipeline:
    """构建默认 Post 风控管道（与原 RiskPostCheckHandler 行为一致）。"""
    return RiskPipeline([
        AmountCheckMiddleware(),
        MaxLeverageMiddleware(),
        PerOrderRatioMiddleware(),
    ])
