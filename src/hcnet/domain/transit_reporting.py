"""Composición Carta de resultados de transporte público, con figuras vectoriales."""

from collections.abc import Mapping, Sequence


def current_records(state):
    return [
        record
        for record in state.get("records", {}).values()
        if isinstance(record, dict) and "title" in record and not record.get("stale")
    ]


def _value(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _escape(text):
    from hcnet.domain.reporting import _latex_escape

    text = _value(text).replace("²", "[2]").replace("³", "[3]").replace("→", " a ")
    return _latex_escape(text.replace("⋅", "·"))


def _table(headers, rows):
    output = []
    for start in range(1, max(2, len(headers)), 3):
        ids = [0, *range(start, min(start + 3, len(headers)))]
        width = 13.8 / len(ids)
        columns = ("p{" + f"{width:.2f}" + "cm}") * len(ids)
        output.extend([r"\begin{small}", r"\begin{longtable}{" + columns + "}", r"\toprule"])
        output.append(" & ".join(r"\textbf{" + _escape(headers[i]) + "}" for i in ids) + r" \\")
        output.extend([r"\midrule", r"\endhead"])
        for values in rows:
            output.append(" & ".join(_escape(values[i]) for i in ids) + r" \\")
        output.extend([r"\bottomrule", r"\end{longtable}", r"\end{small}"])
    return output


def _chart(chart):
    chart_series = {name: points for name, points in chart["series"].items() if points}
    if not chart_series:
        return []
    points = [point for values in chart_series.values() for point in values]
    xmax = max(x for x, _ in points) or 1
    xmax += 0.5 if chart.get("bars") else 0
    ymin, ymax = min(0, min(y for _, y in points)), max(y for _, y in points)
    if ymax <= ymin:
        ymax = ymin + 1
    lines = [
        r"\begin{center}",
        r"\textbf{" + _escape(chart["title"]) + "}",
        r"\par",
        r"\begin{picture}(300,117)",
        r"\Line(42,29)(286,29)\Line(42,29)(42,105)",
        rf"\put(3,108){{\scriptsize {_escape(chart['y'])}}}",
        rf"\put(245,1){{\scriptsize {_escape(chart['x'])}}}",
    ]
    for i in range(5):
        dx, dy = 42 + i * 60, 29 + i * 18
        if not chart.get("bars"):
            lines.append(rf"\put({dx},14){{\scriptsize {xmax * i / 4:.3g}}}")
        lines.append(rf"\put(4,{dy}){{\scriptsize {ymin + (ymax - ymin) * i / 4:.3g}}}")
    legend = []
    colors = ("blue!65!black", "orange!70!black", "green!55!black", "magenta!65!black")
    for i, (name, values) in enumerate(chart_series.items()):
        shade = colors[i % len(colors)]
        legend.append(rf"\textcolor{{{shade}}}{{{_escape(name)}}}")
        step = max(1, len(values) // 180)
        sampled = values[::step]
        if sampled[-1] != values[-1]:
            sampled = [*sampled, values[-1]]
        coords = [(42 + 240 * x / xmax, 29 + 72 * (y - ymin) / (ymax - ymin)) for x, y in sampled]
        lines.append(rf"{{\color{{{shade}}}\linethickness{{0.7pt}}")
        if chart.get("bars"):
            lines.extend(
                rf"\put({x - 12:.2f},29){{\rule{{24pt}}{{{y - 29:.2f}pt}}}}" for x, y in coords
            )
        elif name not in chart.get("markers", []) and len(coords) > 1:
            lines.append(r"\polyline" + "".join(f"({x:.2f},{y:.2f})" for x, y in coords))
        else:
            lines.extend(rf"\put({x:.2f},{y:.2f}){{\circle*{{3}}}}" for x, y in coords)
        lines.append("}")
    lines.extend([r"\end{picture}\par", r"\quad ".join(legend), r"\end{center}"])
    return lines


def _inputs(value, path=()):
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _inputs(item, (*path, key))
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for i, item in enumerate(value, 1):
            yield from _inputs(item, (*path, str(i)))
    else:
        yield (" / ".join(path).replace("_", " "), value)


def section(record, level="section"):
    title = _escape(record["title"])
    result = [rf"\{level}{{{title}}}"]
    for equation in record.get("formulas", []):
        result.append(r"\[" + equation + r"\]")
    if record.get("metrics"):
        result.extend(_table(["Indicador", "Resultado"], list(record["metrics"].items())))
    for note in record.get("notes", []):
        result.append(_escape(note) + r"\par")
    for label, headers, rows in record.get("tables", []):
        if rows:
            result.append(r"\paragraph{" + _escape(label) + "}")
            result.extend(_table(headers, rows))
    for chart in record.get("charts", []):
        result.extend(_chart(chart))
    source = record.get("sources", [])
    if source:
        result.append(r"\paragraph{Fuentes de referencia}")
        for url in source:
            if url.startswith(("https://", "http://")):
                value = url.replace("{", "%7B").replace("}", "%7D").replace("\\", "%5C")
                result.append(r"\url{" + value + r"}\par")
    if record.get("inputs"):
        result.append(r"\paragraph{Datos de entrada}")
        result.extend(_table(["Dato", "Valor"], list(_inputs(record["inputs"]))))
    for child in record.get("included", []):
        result.append(section(child, "subsection"))
    return "\n".join(result)


def report(project, record):
    from hcnet.domain.reporting import _module_latex

    return _module_latex(project, "Transporte público", section(record))
