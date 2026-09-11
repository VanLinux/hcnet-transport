"""Presentación trazable de los resultados matemáticos."""

from __future__ import annotations

from html import escape

from hcnet.domain.models import IntersectionProject, LaneGroupResult


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
        body {{ color: #243447; font-family: sans-serif; font-size: 10pt; }}
        h2 {{ color: #0b3954; margin-bottom: 2px; }}
        h3 {{ color: #176b87; margin-top: 18px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border-bottom: 1px solid #dbe4ea; padding: 5px; text-align: left; }}
        th {{ background: #eef4f7; }}
        .equation {{ background: #f5f8fa; border-left: 4px solid #176b87;
                     font-family: monospace; margin: 6px 0; padding: 8px; }}
        .result {{ color: #0b6e4f; font-weight: bold; }}
        .warning {{ background: #fff3cd; border-left: 4px solid #d99b00; padding: 8px; }}
        .muted {{ color: #60717e; }}
      </style>
    </head>
    <body>
      <h2>{escape(result.label)}</h2>
      <p class="muted">Memoria de cálculo · HCNet Transport 1.0</p>

      <h3>1. Flujo de demanda ajustado</h3>
      <div class="equation">v = V / FHMD<br>
      v = {source.volume_veh_h:.2f} / {source.peak_hour_factor:.3f}
      = <span class="result">{result.demand_flow_rate_veh_h:.2f} veh/h</span></div>

      <h3>2. Factores del flujo de saturación</h3>
      <table>
        <tr><th>Factor</th><th>Valor</th><th>Interpretación</th></tr>
        <tr><td>f<sub>w</sub></td><td>{f.lane_width:.4f}</td><td>Ancho de carril</td></tr>
        <tr><td>f<sub>HV</sub></td><td>{f.heavy_vehicles:.4f}</td><td>Vehículos pesados</td></tr>
        <tr><td>f<sub>g</sub></td><td>{f.grade:.4f}</td><td>Pendiente</td></tr>
        <tr><td>f<sub>p</sub></td><td>{f.parking:.4f}</td><td>Estacionamiento</td></tr>
        <tr><td>f<sub>bb</sub></td><td>{f.bus_blockage:.4f}</td><td>Bloqueos de autobús</td></tr>
        <tr><td>f<sub>LU</sub></td><td>{f.lane_utilization:.4f}</td><td>Uso de carriles</td></tr>
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
      {warnings}
      <p class="muted">La demanda residual es un indicador diagnóstico, no una estimación
      HCM de cola percentil 95. Consulta docs/METHODOLOGY.md para conocer el alcance.</p>
    </body>
    </html>
    """
