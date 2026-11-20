"""Presentación trazable y exportable de los resultados matemáticos."""

from __future__ import annotations

from html import escape

from hcnet import __version__
from hcnet.domain.models import (
    IntersectionProject,
    IntersectionResult,
    LaneGroupInput,
    LaneGroupResult,
)
from hcnet.domain.roundabout import ArmResult, RoundaboutArm, calculate_roundabout
from hcnet.domain.transit import calculate_transit_line


def calculation_trace_html(
    project: IntersectionProject,
    result: LaneGroupResult,
) -> str:
    source = next(group for group in project.lane_groups if group.identifier == result.identifier)
    f = result.factors
    cycle = project.cycle_length_s
    period = project.analysis_period_h
    green_ratio = source.effective_green_s / cycle

    warnings = ""
    if result.warnings:
        items = "".join(f"<li>{escape(message)}</li>" for message in result.warnings)
        warnings = f"<div class='warning'><strong>Observaciones</strong><ul>{items}</ul></div>"

    return f"""
    <html>
    <head>
      <style>
        body {{ color: #202124; font-family: sans-serif; font-size: 10pt; }}
        h2 {{ color: #202124; margin-bottom: 2px; }}
        h3 {{ color: #3f444b; margin-top: 18px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border-bottom: 1px solid #dadce0; padding: 5px; text-align: left; }}
        th {{ background: #eceef0; color: #30343b; }}
        .equation {{ background: #f5f5f5; border-left: 4px solid #5f6368;
                     font-family: monospace; margin: 6px 0; padding: 8px; }}
        .result {{ color: #176b45; font-weight: bold; }}
        .warning {{ background: #f1f3f4; border-left: 4px solid #7a7f85; padding: 8px; }}
        .muted {{ color: #5f6368; }}
      </style>
    </head>
    <body>
      <h2>{escape(result.label)}</h2>
      <p class="muted">Memoria de cálculo · HCNet Transport {__version__}</p>

      <h3>1. Flujo de demanda ajustado</h3>
      <div class="equation">v = V / FHMD<br>
      v = {source.volume_veh_h:.2f} / {source.peak_hour_factor:.3f}
      = <span class="result">{result.demand_flow_rate_veh_h:.2f} veh/h</span></div>

      <h3>2. Factores del flujo de saturación</h3>
      <table>
        <tr><th>Factor</th><th>Valor</th><th>Interpretación</th></tr>
        <tr><td>f<sub>w</sub></td><td>{f.lane_width:.4f}</td><td>Ancho de carril</td></tr>
        <tr><td>f<sub>HV</sub></td><td>{f.heavy_vehicles:.4f}</td>
            <td>Vehículos pesados</td></tr>
        <tr><td>f<sub>g</sub></td><td>{f.grade:.4f}</td><td>Pendiente</td></tr>
        <tr><td>f<sub>p</sub></td><td>{f.parking:.4f}</td><td>Estacionamiento</td></tr>
        <tr><td>f<sub>bb</sub></td><td>{f.bus_blockage:.4f}</td>
            <td>Bloqueos de autobús</td></tr>
        <tr><td>f<sub>LU</sub></td><td>{f.lane_utilization:.4f}</td>
            <td>Uso de carriles</td></tr>
        <tr><td>f<sub>a</sub></td><td>{f.area_type:.4f}</td><td>Tipo de área</td></tr>
        <tr><td>f<sub>turn</sub></td><td>{f.turn:.4f}</td><td>Giro</td></tr>
        <tr><th>Producto</th><th>{f.product:.4f}</th><th></th></tr>
      </table>
      <div class="equation">s = s₀ · N · Πf<br>
      s = {source.base_saturation_flow_pc_h_ln:.2f} · {source.lanes} · {f.product:.4f}
      = <span class="result">{result.saturation_flow_veh_h:.2f} veh/h</span></div>

      <h3>3. Capacidad y grado de saturación</h3>
      <div class="equation">g/C = {source.effective_green_s:.2f} / {cycle:.2f}
      = {green_ratio:.4f}<br>
      c = s(g/C) = {result.saturation_flow_veh_h:.2f}({green_ratio:.4f})
      = <span class="result">{result.capacity_veh_h:.2f} veh/h</span><br>
      X = v/c = {result.demand_flow_rate_veh_h:.2f} / {result.capacity_veh_h:.2f}
      = <span class="result">{result.degree_of_saturation:.4f}</span></div>

      <h3>4. Demora de control</h3>
      <div class="equation">d₁ = 0.5C(1-g/C)² / [1-min(1,X)g/C] · PF<br>
      d₁ = <span class="result">{result.uniform_delay_s_veh:.2f} s/veh</span></div>
      <div class="equation">d₂ = 900T[(X-1)+√((X-1)²+8kIX/(cT))]<br>
      T = {period:.2f} h; k = {source.incremental_delay_factor:.3f};
      I = {source.upstream_filtering_factor:.3f}<br>
      d₂ = <span class="result">{result.incremental_delay_s_veh:.2f} s/veh</span></div>
      <div class="equation">d = d₁ + d₂ + d₃<br>
      d = {result.uniform_delay_s_veh:.2f} + {result.incremental_delay_s_veh:.2f}
      + {result.initial_queue_delay_s_veh:.2f}
      = <span class="result">{result.control_delay_s_veh:.2f} s/veh</span></div>

      <h3>5. Nivel de servicio</h3>
      <p>Resultado del grupo: <span class="result">LOS {result.level_of_service}</span>.</p>
      <p>Llegadas estimadas durante el rojo: {result.red_arrivals_veh_cycle:.2f} veh/ciclo.<br>
      Demanda residual al final del periodo: {result.residual_demand_veh:.2f} veh.</p>

      <h3>6. Cola y tiempo de viaje</h3>
      <div class="equation">Q<sub>media</sub> = R + 0.5q<sub>rojo</sub>
      = <span class="result">{result.average_queue_veh:.2f} veh</span><br>
      Q<sub>95</sub> ≈ R + q<sub>rojo</sub> + 1.645√q<sub>rojo</sub>
      = <span class="result">{result.queue_95_veh:.2f} veh</span><br>
      L<sub>95</sub> = Q<sub>95</sub>e/N
      = <span class="result">{result.queue_95_m:.2f} m</span></div>
      <div class="equation">t₀ = 3.6L/VFL
      = <span class="result">{result.free_flow_travel_time_s:.2f} s</span><br>
      t<sub>viaje</sub> = t₀ + d
      = <span class="result">{result.travel_time_s:.2f} s</span></div>
      {warnings}
      <p class="muted">La demanda residual es un indicador diagnóstico, no una estimación
      HCM de cola percentil 95. Q95 es una aproximación probabilística para diagnóstico
      y almacenamiento; consulta docs/METHODOLOGY.md para conocer el alcance.</p>
    </body>
    </html>
    """


def latex_report(project: IntersectionProject, result: IntersectionResult) -> str:
    """Genera un reporte técnico autocontenido y compilable con PDFLaTeX."""

    analyst = _latex_escape(project.analyst.strip() or "No especificado")
    project_name = _latex_escape(project.name.strip() or "Proyecto sin nombre")
    location = _latex_escape(project.location.strip() or "No especificada")
    study_date = _latex_escape(project.study_date.strip() or "No especificada")
    notes = _latex_escape(project.notes.strip() or "Sin notas registradas.").replace(
        "\n", "\n\n"
    )

    summary_rows = "\n".join(
        (
            f"{_latex_escape(row.label)} & {row.demand_flow_rate_veh_h:.1f} & "
            f"{row.saturation_flow_veh_h:.1f} & {row.capacity_veh_h:.1f} & "
            f"{row.degree_of_saturation:.3f} & {row.control_delay_s_veh:.1f} & "
            f"{row.level_of_service} & {row.queue_95_m:.1f} & {row.travel_time_s:.1f} \\\\"
        )
        for row in result.lane_groups
    )

    branch_rows = "\n".join(
        f"{_latex_escape(branch.code)} & {_latex_escape(branch.name)} & "
        f"{_latex_escape(branch.position)} & {branch.azimuth:.2f} & "
        f"{branch.inbound_lanes} & {branch.outbound_lanes} \\\\"
        for branch in project.active_branches
    )
    group_labels = {group.identifier: group.label for group in project.lane_groups}
    signal_lines = []
    for head in project.signal_heads:
        controlled = ", ".join(
            group_labels.get(item, item) for item in head.controlled_group_ids
        )
        signal_lines.append(
            f"{_latex_escape(head.name)} & {_latex_escape(head.branch_code)} & "
            f"{_latex_escape(head.signal_type)} & {head.signal_phase} & "
            f"{_latex_escape(controlled)} \\\\"
        )
    signal_rows = "\n".join(signal_lines) or r"No configurados & --- & --- & --- & --- \\"

    warning_items = result.warnings or ("Sin advertencias automáticas.",)
    warnings = "\n".join(f"  \\item {_latex_escape(item)}" for item in warning_items)

    groups_by_id = {group.identifier: group for group in project.lane_groups}
    detail_sections = "\n".join(
        _lane_group_latex(groups_by_id[row.identifier], row, project)
        for row in result.lane_groups
    )
    optimization = project.signal_optimization
    plan = ""
    if optimization is not None:
        phases = ", ".join(
            f"F{row.phase_number}: {row.green_s:.1f} s de verde" for row in optimization.phases
        )
        plan = f"Ciclo optimizado: {optimization.cycle_length_s:.1f} s. {phases}."

    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage{{amsmath}}
\usepackage{{booktabs}}
\usepackage{{longtable}}
\usepackage[table]{{xcolor}}
\usepackage[a4paper,margin=2.2cm]{{geometry}}
\usepackage[hidelinks]{{hyperref}}
\usepackage{{fancyhdr}}

\definecolor{{hcDark}}{{HTML}}{{20242A}}
\definecolor{{hcMid}}{{HTML}}{{5F6368}}
\definecolor{{hcLight}}{{HTML}}{{ECEDEF}}
\renewcommand{{\arraystretch}}{{1.15}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{5pt}}
\setlength{{\headheight}}{{14pt}}
\pagestyle{{fancy}}
\fancyhf{{}}
\fancyhead[L]{{\textcolor{{hcMid}}{{HCNet Transport {__version__}}}}}
\fancyhead[R]{{\textcolor{{hcMid}}{{Reporte técnico}}}}
\fancyfoot[C]{{\thepage}}

\begin{{document}}

\begin{{titlepage}}
  \color{{hcDark}}
  \vspace*{{2.2cm}}
  {{\Huge\bfseries HCNet Transport\par}}
  \vspace{{0.25cm}}
  {{\Large Reporte de capacidad, operación y nivel de servicio\par}}
  \vspace{{1.2cm}}
  \rule{{\textwidth}}{{1.2pt}}
  \vspace{{0.8cm}}

  {{\LARGE\bfseries {project_name}\par}}
  \vspace{{0.35cm}}
  {{\large {location}\par}}

  \vfill
  \begin{{tabular}}{{@{{}}ll@{{}}}}
    \textbf{{Analista}} & {analyst} \\
    \textbf{{Fecha del estudio}} & {study_date} \\
    \textbf{{Versión del software}} & {__version__} \\
    \textbf{{Licencia}} & GNU General Public License v3.0 \\
  \end{{tabular}}

  \vspace{{1.2cm}}
  {{\small Desarrollador: Héctor Alonso Benítez García\par}}
\end{{titlepage}}

\section{{Identificación y parámetros}}
\begin{{tabular}}{{@{{}}ll@{{}}}}
  \textbf{{Proyecto}} & {project_name} \\
  \textbf{{Ubicación}} & {location} \\
  \textbf{{Analista}} & {analyst} \\
  \textbf{{Fecha del estudio}} & {study_date} \\
  \textbf{{Longitud de ciclo, $C$}} & {project.cycle_length_s:.1f} s \\
  \textbf{{Periodo de análisis, $T$}} & {project.analysis_period_h:.2f} h \\
  \textbf{{Grupos de carriles}} & {len(project.lane_groups)} \\
  \textbf{{Tipo de intersección}} & {project.branch_count} ramales \\
\end{{tabular}}

\subsection{{Geometría por ramal}}
\begin{{tabular}}{{llcrrr}}
\toprule
Letra & Ramal & Ubicación & Azimut ($^\circ$) & Entrada & Salida \\
\midrule
{branch_rows}
\bottomrule
\end{{tabular}}

\subsection{{Notas del proyecto}}
{notes}

\section{{Resumen de la intersección}}
\begin{{tabular}}{{@{{}}ll@{{}}}}
  \textbf{{Volumen total de entrada}} &
    {result.total_entering_volume_veh_h:.1f} veh/h \\
  \textbf{{Demora de control ponderada}} &
    {result.weighted_control_delay_s_veh:.1f} s/veh \\
  \textbf{{Nivel de servicio}} & {result.level_of_service} \\
  \textbf{{Grado de saturación crítico}} &
    {result.critical_degree_of_saturation:.3f} \\
  \textbf{{Grupo crítico}} & {_latex_escape(result.critical_lane_group)} \\
  \textbf{{Cola P95 máxima aproximada}} & {result.maximum_queue_95_m:.1f} m \\
  \textbf{{Tiempo de viaje ponderado}} & {result.weighted_travel_time_s:.1f} s \\
\end{{tabular}}

\section{{Resultados por grupo de carriles}}
\scriptsize
\begin{{longtable}}{{@{{}}p{{3.4cm}}rrrrrrrr@{{}}}}
\toprule
Grupo & $v$ & $s$ & $c$ & $X$ & $d$ & LOS & $L_{{95}}$ & $t$ \\
 & veh/h & veh/h & veh/h &  & s/veh & & m & s \\
\midrule
\endfirsthead
\toprule
Grupo & $v$ & $s$ & $c$ & $X$ & $d$ & LOS & $L_{{95}}$ & $t$ \\
\midrule
\endhead
{summary_rows}
\bottomrule
\end{{longtable}}
\normalsize

\section{{Configuración semafórica}}
Método seleccionado: \textbf{{{_latex_escape(project.optimization_method)}}}. Tiempo perdido
por fase: {project.signal_lost_time_s:.1f} s; verde mínimo: {project.minimum_green_s:.1f} s;
amarillo: {project.yellow_time_s:.1f} s; todo rojo: {project.all_red_time_s:.1f} s.

\small
\begin{{longtable}}{{p{{3.0cm}}p{{1.1cm}}p{{3.0cm}}rp{{6.0cm}}}}
\toprule
Semáforo & Ramal & Tipo & Fase & Movimientos controlados \\
\midrule
{signal_rows}
\bottomrule
\end{{longtable}}
\normalsize
{plan}

\section{{Memoria de cálculo}}
{detail_sections}

\section{{Diagnóstico automático}}
\begin{{itemize}}
{warnings}
\end{{itemize}}

\section{{Alcance metodológico}}
El reporte corresponde al análisis de una intersección semaforizada aislada con
control de tiempo fijo. HCNet Transport es una herramienta educativa independiente:
no está afiliada ni certificada por TRB, National Academies, McTrans Center o HCS.
Los resultados deben contrastarse con una fuente metodológica autorizada antes de
emplearse en estudios profesionales.

\vfill
\begin{{center}}
\small\textcolor{{hcMid}}{{Generado con HCNet Transport {__version__} ·
Software libre bajo GNU GPL v3.0}}
\end{{center}}

\end{{document}}
"""


def _module_latex(project: IntersectionProject, title: str, content: str) -> str:
    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[margin=2cm]{{geometry}}
\usepackage{{booktabs,longtable,amsmath}}
\setlength{{\parindent}}{{0pt}}
\begin{{document}}
\section*{{HCNet Transport {__version__} · {title}}}
\textbf{{Analista}}: {_latex_escape(project.analyst)}\par
\textbf{{Proyecto}}: {_latex_escape(project.name or "Sin nombre")}\par
\textbf{{Fecha}}: {_latex_escape(project.study_date)}\par
{content}
\end{{document}}
"""


def transit_latex(project: IntersectionProject) -> str:
    return _module_latex(project, "Transporte público", _transit_latex(project))


def _transit_latex(project: IntersectionProject) -> str:

    data = project.public_transport
    result = calculate_transit_line(data)

    congestion_rows = "\n".join(
        f"{_latex_escape(row.model)} & "
        + (
            r"No finito & --- & --- \\"
            if row.travel_time_min is None
            else f"{row.travel_time_min:.2f} & {row.delay_min:.2f} & "
            f"{row.commercial_speed_kmh:.2f} \\\\"
        )
        for row in result.congestion
    )
    warnings = result.warnings or ("Sin advertencias automáticas.",)
    warning_items = "\n".join(f"  \\item {_latex_escape(item)}" for item in warnings)
    required_headway = (
        "---" if result.required_frequency_bus_h == 0 else f"{result.required_headway_min:.2f}"
    )
    return rf"""
\section{{Transporte público}}
\begin{{tabular}}{{@{{}}ll@{{}}}}
  \textbf{{Línea}} & {_latex_escape(data.name or "Sin nombre")} \\
  \textbf{{Longitud por sentido}} & {data.route_length_km:.2f} km \\
  \textbf{{Velocidad de operación}} & {result.operating_speed_kmh:.2f} km/h \\
  \textbf{{Velocidad comercial}} & {result.commercial_speed_kmh:.2f} km/h \\
  \textbf{{Tiempo comercial por sentido}} & {result.commercial_time_one_way_min:.2f} min \\
  \textbf{{Tiempo de ciclo}} & {result.cycle_time_min:.2f} min \\
  \textbf{{Frecuencia programada}} & {result.service_frequency_bus_h:.2f} bus/h \\
  \textbf{{Capacidad de línea}} & {result.line_capacity_pax_h_direction:.1f} pax/h/sentido \\
  \textbf{{Frecuencia requerida}} & {result.required_frequency_bus_h:.2f} bus/h \\
  \textbf{{Intervalo requerido}} & {required_headway} min \\
  \textbf{{Flota mínima + reserva}} & {result.minimum_fleet_veh} +
    {result.reserve_fleet_veh} = {result.total_fleet_veh} vehículos \\
  \textbf{{Espaciamiento actual / óptimo}} & {result.actual_stop_spacing_m:.0f} /
    {result.optimal_stop_spacing_m:.0f} m \\
  \textbf{{Acceso peatonal medio}} & {result.average_access_time_min:.2f} min \\
  \textbf{{Permanencia en parada}} & {result.dwell_time_s:.2f} s \\
  \textbf{{Ascenso / descenso}} & {result.boarding_service_time_s:.2f} /
    {result.alighting_service_time_s:.2f} s \\
  \textbf{{Margen de oferta}} & {result.capacity_margin_pax_h_direction:+.1f} pax/h/sentido \\
  \textbf{{Capacidad de parada crítica}} & {result.critical_stop_capacity_bus_h:.2f} bus/h \\
  \textbf{{Saturación vial equivalente}} & {result.road_degree_of_saturation:.3f} \\
\end{{tabular}}

\subsection{{Comparación de funciones de congestión}}
\begin{{tabular}}{{lrrr}}
\toprule
Modelo & Tiempo (min) & Demora (min) & Velocidad (km/h) \\
\midrule
{congestion_rows}
\bottomrule
\end{{tabular}}

\subsection{{Diagnóstico de la línea}}
\begin{{itemize}}
{warning_items}
\end{{itemize}}
"""


def roundabout_latex(project: IntersectionProject) -> str:
    data = project.roundabout
    result = calculate_roundabout(data)
    rows = "\n".join(
        f"{a.code} & {a.entry:.1f} & {a.exiting:.1f} & {a.conflicting_equivalent:.1f} & "
        f"{a.capacity:.1f} & {a.saturation:.3f} & {a.delay:.1f} & "
        f"{_latex_escape(a.los)} & {a.queue_95:.1f} & {a.queue_95_m:.1f} " + r"\\"
        for a in result.arms
    )

    def geometry_row(arm: RoundaboutArm, row: ArmResult) -> str:
        values = (
            arm.azimuth_deg, arm.entry_width_m or None, arm.exit_width_m or None,
            row.entry_radius, row.exit_radius, row.entry_speed,
            row.exit_speed, row.next_angle, row.arc_length,
        )
        return (
            row.code + " & "
            + " & ".join("---" if v is None else f"{v:.2f}" for v in values) + r" \\"
        )

    geometry = "\n".join(
        geometry_row(arm, row) for arm, row in zip(data.arms, result.arms, strict=False)
    )
    matrix_columns = "r" * (data.arm_count + 1)
    codes = " & ".join(row.code for row in result.arms)
    matrix = "\n".join(
        r.code + " & " + " & ".join(f"{v:g}" for v in row[:data.arm_count]) + r" \\"
        for r, row in zip(result.arms, data.flows, strict=False)
    )
    warnings = "\n\n".join(_latex_escape(w) for w in result.warnings)
    return _module_latex(project, "Rotondas", rf"""
\subsection*{{{_latex_escape(data.name or "Rotonda sin nombre")}}}
Rotonda de un carril, {data.arm_count} ramales y sentido {_latex_escape(data.circulation)}.
Demanda ajustada: {result.total_entry:.1f} veh/h.
Demora ponderada: {result.delay:.1f} s/veh. LOS: {_latex_escape(result.los)}.

\subsection*{{Operación por ramal}}
\small
\begin{{longtable}}{{lrrrrrrrrr}}
\toprule
Ramal & Entrada & Salida & Conflicto & Capacidad & $v/c$ & Demora & LOS & P95 & P95 (m) \\
 & veh/h & veh/h & eq/h & veh/h & & s/veh & & veh & m \\
\midrule
{rows}
\bottomrule
\end{{longtable}}
\normalsize

\subsection*{{Geometría preliminar}}
Diámetro inscrito: {data.diameter_m:.2f} m. Ancho anular: {data.circulating_width_m:.2f} m.
Corona montable: {data.apron_width_m:.2f} m. Radio de isla total: {result.island_radius:.2f} m.
Radio de isla no montable: {result.hard_island_radius:.2f} m.
Radio del eje anular: {result.centerline_radius:.2f} m.
Radio mínimo a {data.design_speed_kmh:.1f} km/h: {result.design_min_radius:.2f} m.
Velocidad teórica del eje: {result.centerline_speed:.1f} km/h.
Distancia de visibilidad de parada: {result.stopping_distance:.1f} m.

\small
\begin{{longtable}}{{lrrrrrrrrr}}
\toprule
Ramal & Azimut & Ancho E & Ancho S & Radio E & Radio S & Vel. E & Vel. S & Ángulo & Arco \\
 & $^\circ$ & m & m & m & m & km/h & km/h & $^\circ$ & m \\
\midrule
{geometry}
\bottomrule
\end{{longtable}}
\normalsize

\subsection*{{Aforos origen--destino (veh/h)}}
\begin{{tabular}}{{{matrix_columns}}}
\toprule
O/D & {codes} \\
\midrule
{matrix}
\bottomrule
\end{{tabular}}

\subsection*{{Método y diagnóstico}}
Capacidad exponencial y demora y cola P95 del NCHRP Report 672, capítulo 4.
$A={data.capacity_a:g}$ eq/h, $B={data.capacity_b:g}$ h/eq,
$FHMD={data.peak_hour_factor:g}$, $T={data.period_h:g}$ h.
Los radios de trayectoria proceden de medición directa o de cuerda y flecha.
La geometría es preliminar.

{warnings or "Sin alertas para los datos capturados."}
""")


def _lane_group_latex(
    source: LaneGroupInput,
    result: LaneGroupResult,
    project: IntersectionProject,
) -> str:
    f = result.factors
    green_ratio = source.effective_green_s / project.cycle_length_s
    warning_items = result.warnings or ("Sin advertencias para este grupo.",)
    warnings = "\n".join(f"  \\item {_latex_escape(item)}" for item in warning_items)

    return rf"""
\subsection{{{_latex_escape(result.label)}}}

\begin{{tabular}}{{@{{}}ll@{{}}}}
  Recorrido & {_latex_escape(source.origin_branch)} $\rightarrow$
    {_latex_escape('/'.join(source.destination_branches))} \\
  Carriles asignados & {_latex_escape(', '.join(str(item) for item in source.lane_indices))} \\
  Fase semafórica & {source.signal_phase} \\
  Volumen observado, $V$ & {source.volume_veh_h:.1f} veh/h \\
  Número de carriles, $N$ & {source.lanes} \\
  Verde efectivo, $g$ & {source.effective_green_s:.1f} s \\
  Factor de hora de máxima demanda, FHMD & {source.peak_hour_factor:.3f} \\
  Flujo de saturación base, $s_0$ &
    {source.base_saturation_flow_pc_h_ln:.1f} pc/h/carril \\
\end{{tabular}}

\[
v=\frac{{V}}{{FHMD}}
=\frac{{{source.volume_veh_h:.2f}}}{{{source.peak_hour_factor:.3f}}}
={result.demand_flow_rate_veh_h:.2f}\ \mathrm{{veh/h}}
\]

\begin{{center}}
\begin{{tabular}}{{lrrrrrrrrr}}
\toprule
Factor & $f_w$ & $f_{{HV}}$ & $f_g$ & $f_p$ & $f_{{bb}}$ &
$f_{{LU}}$ & $f_a$ & $f_{{turn}}$ & $\prod f$ \\
\midrule
Valor & {f.lane_width:.4f} & {f.heavy_vehicles:.4f} & {f.grade:.4f} &
{f.parking:.4f} & {f.bus_blockage:.4f} & {f.lane_utilization:.4f} &
{f.area_type:.4f} & {f.turn:.4f} & {f.product:.4f} \\
\bottomrule
\end{{tabular}}
\end{{center}}

\begin{{align*}}
s &= s_0 N \prod f
 = {source.base_saturation_flow_pc_h_ln:.2f}({source.lanes})({f.product:.4f})
 = {result.saturation_flow_veh_h:.2f}\ \mathrm{{veh/h}},\\
\frac{{g}}{{C}} &= \frac{{{source.effective_green_s:.2f}}}
{{{project.cycle_length_s:.2f}}} = {green_ratio:.4f},\\
c &= s\frac{{g}}{{C}} = {result.capacity_veh_h:.2f}\ \mathrm{{veh/h}},\\
X &= \frac{{v}}{{c}} = {result.degree_of_saturation:.4f}.
\end{{align*}}

\begin{{align*}}
d_1 &= {result.uniform_delay_s_veh:.2f}\ \mathrm{{s/veh}},\\
d_2 &= {result.incremental_delay_s_veh:.2f}\ \mathrm{{s/veh}},\\
d_3 &= {result.initial_queue_delay_s_veh:.2f}\ \mathrm{{s/veh}},\\
d &= d_1+d_2+d_3 = {result.control_delay_s_veh:.2f}\ \mathrm{{s/veh}}.
\end{{align*}}

\textbf{{Resultado:}} LOS {result.level_of_service}. Llegadas durante el rojo:
{result.red_arrivals_veh_cycle:.2f} veh/ciclo; demanda residual:
{result.residual_demand_veh:.2f} veh.

\begin{{align*}}
Q_{{media}} &= R + 0.5q_{{rojo}} = {result.average_queue_veh:.2f}\ \mathrm{{veh}},\\
Q_{{95}} &\approx R+q_{{rojo}}+1.645\sqrt{{q_{{rojo}}}}
 = {result.queue_95_veh:.2f}\ \mathrm{{veh}},\\
L_{{95}} &= \frac{{Q_{{95}}}}{{N}}e = {result.queue_95_m:.2f}\ \mathrm{{m}},\\
t_0 &= \frac{{3.6L}}{{VFL}} = {result.free_flow_travel_time_s:.2f}\ \mathrm{{s}},\\
t_{{viaje}} &= t_0+d = {result.travel_time_s:.2f}\ \mathrm{{s}}.
\end{{align*}}

\begin{{itemize}}
{warnings}
\end{{itemize}}
"""


_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "×": r"$\times$",
    "≥": r"$\geq$",
    "≤": r"$\leq$",
    "₀": r"$_0$",
    "₁": r"$_1$",
    "₂": r"$_2$",
    "₃": r"$_3$",
    "–": "--",
    "—": "---",
}


def _latex_escape(value: str) -> str:
    return "".join(_LATEX_ESCAPES.get(character, character) for character in value)
