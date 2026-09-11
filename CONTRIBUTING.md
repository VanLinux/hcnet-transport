# Contribuir a HCNet Transport

HCNet Transport acepta aportaciones que mejoren su rigor matemático, claridad docente,
compatibilidad con Linux y calidad del código.

## Preparación

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## Comprobaciones

Antes de proponer un cambio, ejecuta:

```bash
ruff check .
pytest
```

Todo procedimiento nuevo debe incluir:

1. Definición de entradas, unidades y dominio de validez.
2. Referencia técnica verificable.
3. Caso pequeño reproducible manualmente.
4. Pruebas automatizadas de valores normales y casos límite.
5. Una traza de cálculo comprensible para estudiantes.

No deben copiarse textos, tablas ni material protegido del *Highway Capacity Manual*.
