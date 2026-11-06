"""Ajustes del panel leídos de `config/config.yaml` (sección `dashboard`)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from pingunews.collector.classifier import CATEGORIA_ORDEN


@dataclass(frozen=True)
class AjustesPanel:
    opciones_dias: List[int]
    dias_por_defecto: int
    destacados_cobertura_minima: int
    destacados_max: int
    items_por_pagina: int
    todas_las_categorias: List[str]
    twitter_activo: bool

    @classmethod
    def desde_config(cls, config: dict) -> "AjustesPanel":
        d = config.get("dashboard", {})
        return cls(
            opciones_dias=d.get("opciones_dias", [1, 3, 7, 14, 30]),
            dias_por_defecto=d.get("dias_por_defecto", 3),
            destacados_cobertura_minima=d.get("destacados_cobertura_minima", 2),
            destacados_max=d.get("destacados_max", 8),
            items_por_pagina=d.get("items_por_pagina", 20),
            todas_las_categorias=list(CATEGORIA_ORDEN),
            twitter_activo=config.get("twitter", {}).get("enabled", False),
        )
