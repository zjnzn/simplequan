"""Indicator —— 指标注册表和加载器。"""
from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Any

from core.ports.indicator import Indicator

log = logging.getLogger(__name__)


class IndicatorRegistry:
    """指标注册表。"""

    def __init__(self) -> None:
        self._plugins: dict[str, Indicator] = {}

    def register(self, plugin: Indicator) -> None:
        """注册指标。"""
        if not isinstance(plugin, Indicator):
            raise TypeError(f"{type(plugin).__name__} 未实现 Indicator 协议")
        if plugin.name in self._plugins:
            log.warning("覆盖已有指标: %s", plugin.name)
        self._plugins[plugin.name] = plugin
        log.info("注册指标: %s v%s", plugin.name, plugin.version)

    def get(self, name: str) -> Indicator:
        """获取指标，不存在时抛出 KeyError。"""
        if name not in self._plugins:
            raise KeyError(f"指标 '{name}' 未注册，已注册: {list(self._plugins)}")
        return self._plugins[name]

    def all(self) -> list[Indicator]:
        """获取所有已注册指标。"""
        return list(self._plugins.values())

    def has(self, name: str) -> bool:
        """检查指标是否已注册。"""
        return name in self._plugins

    def filter_by_keys(self, keys: list[str]) -> list[Indicator]:
        """返回能产出指定 key 集合的指标子集。keys 为空时返回全部。"""
        if not keys:
            return self.all()
        key_set = set(keys)
        return [c for c in self.all() if key_set & set(c.output_keys)]

    def __len__(self) -> int:
        """返回已注册指标数量。"""
        return len(self._plugins)


class IndicatorLoader:
    """指标加载器。"""

    def __init__(self, registry: IndicatorRegistry) -> None:
        self._registry = registry

    def load_module(self, dotted_path: str, params: dict[str, Any] | None = None) -> Indicator:
        """从 Python 模块路径加载并实例化指标。"""
        module_path, cls_name = dotted_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            raise ImportError(f"无法导入模块 '{module_path}': {e}") from e

        cls = getattr(module, cls_name, None)
        if cls is None:
            raise AttributeError(f"模块 '{module_path}' 中找不到类 '{cls_name}'")

        indicator = cls(**(params or {}))
        self._registry.register(indicator)
        return indicator

    def load_file(self, spec: str, params: dict[str, Any] | None = None) -> Indicator:
        """从文件路径加载指标。"""
        if "::" not in spec:
            raise ValueError(f"格式错误，需要 'path.py::ClassName'，得到: {spec}")

        file_path, cls_name = spec.split("::", 1)
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"指标文件不存在: {file_path}")

        spec_obj = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec_obj)
        spec_obj.loader.exec_module(module)

        cls = getattr(module, cls_name, None)
        if cls is None:
            raise AttributeError(f"文件 '{file_path}' 中找不到类 '{cls_name}'")

        indicator = cls(**(params or {}))
        self._registry.register(indicator)
        return indicator

    def load_all(self, configs: list[dict[str, Any]]) -> None:
        """从配置列表批量加载指标。"""
        for cfg in configs:
            params = cfg.get("params", {})
            if "module" in cfg:
                self.load_module(cfg["module"], params)
            elif "file" in cfg:
                self.load_file(cfg["file"], params)
            else:
                raise ValueError(f"无效指标配置（需要 'module' 或 'file'）: {cfg}")
