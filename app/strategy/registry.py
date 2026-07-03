"""Strategy —— 策略注册表和加载器（缓存类对象，无状态模板）。"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any

from core.ports.strategy import Strategy

log = logging.getLogger(__name__)


class StrategyRegistry:
    """策略注册表：name → 策略类（无状态模板，不实例化）。"""

    def __init__(self) -> None:
        self._plugins: dict[str, type] = {}

    def register(self, cls: type) -> None:
        """注册策略类。"""
        if not inspect.isclass(cls):
            raise TypeError(f"期望类对象，得到 {type(cls).__name__}")
        name = getattr(cls, "name", None)
        if not name:
            raise AttributeError(f"{cls.__name__} 缺少 name 属性")
        if name in self._plugins:
            log.warning("覆盖已有策略: %s", name)
        self._plugins[name] = cls
        log.info("注册策略: %s v%s", name, getattr(cls, "version", "?"))

    def get(self, name: str) -> type:
        """获取策略类，不存在时抛出 KeyError。"""
        if name not in self._plugins:
            raise KeyError(f"策略 '{name}' 未注册，已注册: {list(self._plugins)}")
        return self._plugins[name]

    def all(self) -> list[type]:
        """获取所有已注册策略类。"""
        return list(self._plugins.values())

    def has(self, name: str) -> bool:
        """检查策略是否已注册。"""
        return name in self._plugins

    def __len__(self) -> int:
        return len(self._plugins)


class StrategyLoader:
    """策略加载器：从模块/文件加载类对象并注册（不实例化）。"""

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    def load_module(self, dotted_path: str) -> type:
        """从 Python 模块路径加载策略类并注册。"""
        module_path, cls_name = dotted_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            raise ImportError(f"无法导入模块 '{module_path}': {e}") from e

        cls = getattr(module, cls_name, None)
        if cls is None or not inspect.isclass(cls):
            raise AttributeError(f"模块 '{module_path}' 中找不到类 '{cls_name}'")

        self._registry.register(cls)
        return cls

    def load_file(self, spec: str) -> type:
        """从文件路径加载策略类。"""
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
        if cls is None or not inspect.isclass(cls):
            raise AttributeError(f"文件 '{file_path}' 中找不到类 '{cls_name}'")

        self._registry.register(cls)
        return cls

    def load_all(self, configs: list[dict[str, Any]]) -> None:
        """从配置列表批量加载策略类（仅 module/file，不接 params）。"""
        for cfg in configs:
            if "module" in cfg:
                self.load_module(cfg["module"])
            elif "file" in cfg:
                self.load_file(cfg["file"])
            else:
                raise ValueError(f"无效策略配置（需要 'module' 或 'file'）: {cfg}")
