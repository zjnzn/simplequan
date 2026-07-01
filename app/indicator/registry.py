from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Any

from core.ports.indicator import Indicator


log = logging.getLogger(__name__)


class IndicatorRegistry:
    """指标计算器注册表。"""

    def __init__(self) -> None:
        self._plugins: dict[str, Indicator] = {}

    def register(self, calculator: Indicator) -> None:
        if not isinstance(calculator, Indicator):
            raise TypeError(
                f"{type(calculator).__name__} 未实现 Indicator 协议"
            )
        if calculator.name in self._plugins:
            log.warning("覆盖已有指标计算器: %s", calculator.name)
        self._plugins[calculator.name] = calculator
        log.info("注册指标计算器: %s v%s", calculator.name, calculator.version)

    def get(self, name: str) -> Indicator:
        if name not in self._plugins:
            raise KeyError(f"指标计算器 '{name}' 未注册，已注册: {list(self._plugins)}")
        return self._plugins[name]

    def all(self) -> list[Indicator]:
        return list(self._plugins.values())

    def has(self, name: str) -> bool:
        return name in self._plugins

    def filter_by_keys(self, keys: list[str]) -> list[Indicator]:
        """返回能产出指定 key 集合的计算器子集。

        keys 为空时返回全部计算器。
        """
        if not keys:
            return self.all()
        key_set = set(keys)
        return [c for c in self.all() if key_set & set(c.output_keys)]

    def __len__(self) -> int:
        return len(self._plugins)


class IndicatorLoader:
    """从模块路径或文件路径动态加载指标计算器。"""

    def __init__(self, registry: IndicatorRegistry) -> None:
        self._registry = registry

    def load_module(self, dotted_path: str,
                    params: dict[str, Any] | None = None) -> Indicator:
        """从 Python 模块路径加载并实例化指标计算器。

        dotted_path: "src.indicators.ma.MaCalculator"
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

        calculator = cls(**(params or {}))
        self._registry.register(calculator)
        return calculator

    def load_file(self, spec: str,
                  params: dict[str, Any] | None = None) -> Indicator:
        """从文件路径加载指标计算器。

        spec: "/path/to/calc.py::ClassName"
        """
        if "::" not in spec:
            raise ValueError(f"格式错误，需要 'path.py::ClassName'，得到: {spec}")

        file_path, cls_name = spec.split("::", 1)
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"指标计算器文件不存在: {file_path}")

        spec_obj = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec_obj)
        spec_obj.loader.exec_module(module)

        cls = getattr(module, cls_name, None)
        if cls is None:
            raise AttributeError(f"文件 '{file_path}' 中找不到类 '{cls_name}'")

        calculator = cls(**(params or {}))
        self._registry.register(calculator)
        return calculator

    def load_all(self, configs: list[dict[str, Any]]) -> None:
        """从配置列表批量加载指标计算器。"""
        for cfg in configs:
            params = cfg.get("params", {})
            if "module" in cfg:
                self.load_module(cfg["module"], params)
            elif "file" in cfg:
                self.load_file(cfg["file"], params)
            else:
                raise ValueError(f"无效指标配置（需要 'module' 或 'file'）: {cfg}")
