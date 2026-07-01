from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Any

from src.strategies.base import Strategy

log = logging.getLogger(__name__)


class StrategyRegistry:
    """策略注册表。"""

    def __init__(self) -> None:
        self._plugins: dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        if not isinstance(strategy, Strategy):
            raise TypeError(
                f"{type(strategy).__name__} 未实现 Strategy 协议"
            )
        if strategy.name in self._plugins:
            log.warning("覆盖已有策略: %s", strategy.name)
        self._plugins[strategy.name] = strategy
        log.info("注册策略: %s v%s", strategy.name, strategy.version)

    def get(self, name: str) -> Strategy:
        if name not in self._plugins:
            raise KeyError(f"策略 '{name}' 未注册，已注册: {list(self._plugins)}")
        return self._plugins[name]

    def all(self) -> list[Strategy]:
        return list(self._plugins.values())

    def has(self, name: str) -> bool:
        return name in self._plugins

    def collect_required_indicators(self) -> set[str]:
        """收集所有策略的 required_indicators 合并集合。"""
        result: set[str] = set()
        for s in self._plugins.values():
            result.update(s.required_indicators)
        return result

    def __len__(self) -> int:
        return len(self._plugins)


class StrategyLoader:
    """从模块路径或文件路径动态加载策略。"""

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    def load_module(self, dotted_path: str,
                    params: dict[str, Any] | None = None) -> Strategy:
        module_path, cls_name = dotted_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            raise ImportError(f"无法导入模块 '{module_path}': {e}") from e

        cls = getattr(module, cls_name, None)
        if cls is None:
            raise AttributeError(f"模块 '{module_path}' 中找不到类 '{cls_name}'")

        strategy = cls(**(params or {}))
        self._registry.register(strategy)
        return strategy

    def load_file(self, spec: str,
                  params: dict[str, Any] | None = None) -> Strategy:
        if "::" not in spec:
            raise ValueError(f"格式错误，需要 'path.py::ClassName'，得到: {spec}")

        file_path, cls_name = spec.split("::", 1)
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"策略文件不存在: {file_path}")

        spec_obj = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec_obj)
        spec_obj.loader.exec_module(module)

        cls = getattr(module, cls_name, None)
        if cls is None:
            raise AttributeError(f"文件 '{file_path}' 中找不到类 '{cls_name}'")

        strategy = cls(**(params or {}))
        self._registry.register(strategy)
        return strategy

    def load_all(self, configs: list[dict[str, Any]]) -> None:
        for cfg in configs:
            params = cfg.get("params", {})
            if "module" in cfg:
                self.load_module(cfg["module"], params)
            elif "file" in cfg:
                self.load_file(cfg["file"], params)
            else:
                raise ValueError(f"无效策略配置（需要 'module' 或 'file'）: {cfg}")
