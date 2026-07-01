"""Strategy —— 策略注册表和加载器。"""
from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Any

from core.ports.strategy import Strategy

log = logging.getLogger(__name__)


class StrategyRegistry:
    """策略注册表。"""

    def __init__(self) -> None:
        self._plugins: dict[str, Strategy] = {}

    def register(self, plugin: Strategy) -> None:
        """注册策略。"""
        if not isinstance(plugin, Strategy):
            raise TypeError(f"{type(plugin).__name__} 未实现 Strategy 协议")
        if plugin.name in self._plugins:
            log.warning("覆盖已有策略: %s", plugin.name)
        self._plugins[plugin.name] = plugin
        log.info("注册策略: %s v%s", plugin.name, plugin.version)

    def get(self, name: str) -> Strategy:
        """获取策略，不存在时抛出 KeyError。"""
        if name not in self._plugins:
            raise KeyError(f"策略 '{name}' 未注册，已注册: {list(self._plugins)}")
        return self._plugins[name]

    def all(self) -> list[Strategy]:
        """获取所有已注册策略。"""
        return list(self._plugins.values())

    def has(self, name: str) -> bool:
        """检查策略是否已注册。"""
        return name in self._plugins

    def collect_required_indicators(self) -> set[str]:
        """收集所有策略的 required_indicators 合并集合。"""
        result: set[str] = set()
        for s in self._plugins.values():
            result.update(s.required_indicators)
        return result

    def __len__(self) -> int:
        """返回已注册策略数量。"""
        return len(self._plugins)


class StrategyLoader:
    """策略加载器。"""

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    def load_module(self, dotted_path: str, params: dict[str, Any] | None = None) -> Strategy:
        """从 Python 模块路径加载并实例化策略。"""
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

    def load_file(self, spec: str, params: dict[str, Any] | None = None) -> Strategy:
        """从文件路径加载策略。"""
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
        """从配置列表批量加载策略。"""
        for cfg in configs:
            params = cfg.get("params", {})
            if "module" in cfg:
                self.load_module(cfg["module"], params)
            elif "file" in cfg:
                self.load_file(cfg["file"], params)
            else:
                raise ValueError(f"无效策略配置（需要 'module' 或 'file'）: {cfg}")
