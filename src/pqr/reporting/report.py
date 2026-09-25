"""Self-contained HTML research notebook, with no remote scripts or fonts."""

import re
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
from jinja2 import Environment, FileSystemLoader, select_autoescape

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from pqr.evaluation.metrics import concentration, linked_contributions, rolling_returns

if TYPE_CHECKING:
    from pqr.pipeline import ResearchRun

COLORS = {"Strategy": "#156d54", "Equal weight": "#8f897c", "Benchmark": "#a8a06a"}


def svg_chart(fig: plt.Figure) -> str:
    stream = StringIO()
    fig.savefig(stream, format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)
    contents = stream.getvalue()
    svg = contents[contents.index("<svg") :]
    prefix = "chart-" + sha256(svg.encode()).hexdigest()[:12] + "-"
    for identity in re.findall(r'id="([^"]+)"', svg):
        svg = svg.replace(f'id="{identity}"', f'id="{prefix}{identity}"')
        svg = svg.replace(f'href="#{identity}"', f'href="#{prefix}{identity}"')
        svg = svg.replace(f"url(#{identity})", f"url(#{prefix}{identity})")
    return svg


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor("#fcfbf7")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#deded2")
    ax.grid(axis="y", color="#e9e7de", linewidth=0.6)
    ax.tick_params(axis="both", labelsize=8, colors="#65665c", length=0, pad=8)
    ax.set_axisbelow(True)


def make_charts(run: "ResearchRun") -> dict[str, str]:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "svg.fonttype": "none",
            "svg.hashsalt": "pqr-v1",
            "figure.facecolor": "#fcfbf7",
        }
    )
    charts: dict[str, str] = {}
    fig, ax = plt.subplots(figsize=(10.7, 3.7))
    for name, result in run.results.items():
        ax.plot(
            result.ledger.index,
            result.ledger["nav"] / result.initial_nav * 100,
            label=name,
            color=COLORS[name],
            linewidth=1.7 if name == "Strategy" else 1.1,
        )
    style_axis(ax)
    ax.set_ylabel("Indexed NAV · initial capital = 100", fontsize=9, color="#65665c")
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncol=3)
    charts["equity"] = svg_chart(fig)
    primary = run.results["Strategy"]
    fig, ax = plt.subplots(figsize=(10.7, 2.0))
    wealth = primary.ledger["nav"] / primary.initial_nav
    dd = wealth / wealth.cummax().clip(lower=1) - 1
    ax.fill_between(dd.index, dd.to_numpy(), 0, color="#156d54", alpha=0.16)
    ax.plot(dd.index, dd, color="#156d54", linewidth=1)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    style_axis(ax)
    charts["drawdown"] = svg_chart(fig)
    fig, ax = plt.subplots(figsize=(10.7, 2.4))
    rolling = rolling_returns(primary.ledger["return"])
    ax.plot(rolling.index, rolling["252_session"], color="#156d54", linewidth=1.3)
    ax.axhline(0, color="#8f897c", linewidth=0.6)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    style_axis(ax)
    charts["rolling"] = svg_chart(fig)
    fig, ax = plt.subplots(figsize=(5.0, 2.7))
    monthly = primary.ledger["turnover"].resample("ME").sum()
    ax.bar(monthly.index, monthly, width=20, color="#156d54", alpha=0.8)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    style_axis(ax)
    charts["turnover"] = svg_chart(fig)
    fig, ax = plt.subplots(figsize=(5.0, 2.7))
    ax.fill_between(
        primary.ledger.index, primary.ledger["gross_exposure"], color="#156d54", alpha=0.2
    )
    ax.plot(primary.ledger.index, primary.ledger["gross_exposure"], color="#156d54", linewidth=1)
    ax.set_ylim(0, 1.02)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    style_axis(ax)
    charts["exposure"] = svg_chart(fig)
    return charts


def render_report(run: "ResearchRun") -> Path:
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["percent"] = lambda v: "—" if v is None else f"{v:.2%}"
    env.filters["number"] = lambda v: "—" if v is None else f"{v:,.2f}"
    columns = [
        ("total_return", "Total return", "percent"),
        ("cagr", "CAGR", "percent"),
        ("annualized_volatility", "Annualized volatility", "percent"),
        ("sharpe", "Sharpe · rf = 0", "number"),
        ("sortino", "Sortino · target = 0", "number"),
        ("max_drawdown", "Maximum drawdown", "percent"),
        ("calmar", "Calmar", "number"),
        ("annualized_turnover", "Annualized traded-notional turnover", "percent"),
        ("total_half_turnover", "Cumulative half-turnover", "number"),
        ("mean_gross_exposure", "Average gross exposure", "percent"),
        ("mean_net_exposure", "Average net exposure", "percent"),
        ("hit_rate", "Positive daily returns", "percent"),
        ("cost_usd", "Total costs · USD", "number"),
    ]
    rows = [
        {"label": label, "values": [env.filters[fmt](m[key]) for m in run.metrics.values()]}
        for key, label, fmt in columns
    ]
    coverage = run.features["exclusion_reason"].replace("", "eligible").value_counts().to_dict()
    attribution = linked_contributions(run.results["Strategy"])
    risk = concentration(run.results["Strategy"].weights)
    annual = run.yearly.pivot(index="year", columns="strategy", values="return")
    synthetic = run.manifest["dataset"]["kind"] == "synthetic_fixture"
    text = env.get_template("report.html").render(
        run=run,
        charts=make_charts(run),
        metric_rows=rows,
        coverage=coverage,
        attribution=attribution.head(8).items(),
        risk=risk,
        synthetic=synthetic,
        annual=annual,
        sensitivity=run.sensitivity.to_dict("records"),
        title="Verification notebook" if synthetic else "Research notebook",
    )
    output = run.output / "report.html"
    output.write_text(text)
    return output
