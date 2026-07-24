# strategies package

import importlib, pkgutil, os

def discover_strategies():
    """自动发现 strategies/ 下的所有策略模块"""
    strategies = {}
    path = os.path.dirname(__file__)
    for importer, modname, ispkg in pkgutil.iter_modules([path]):
        if modname.startswith('_'):
            continue
        module = importlib.import_module(f"strategies.{modname}")
        if hasattr(module, "get_signals"):
            name = getattr(module, "STRATEGY_NAME", modname)
            strategies[name] = module.get_signals
    return strategies
