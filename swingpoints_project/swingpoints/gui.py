"""Optional Tkinter interface; the core program also runs without a display."""

from pathlib import Path
from dataclasses import fields
from .indicators import IndicatorSettings, calculate_indicators
from .indicator_plotting import draw_indicators
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from .data import DataError, load_prices
from .methods import METHODS, TraditionalTAMethod, TASettings
from .pipeline import analyze
from .breakouts import BreakoutSettings
from .breakout_plotting import draw_breakouts
from .output import export_results
from .plotting import draw_prices
from .trendlines import TrendSettings, detect_trendlines, select_trendlines


class SwingApp:
    """File picker, configurable detector, historical cutoff, chart and table."""

    def __init__(self, root, window=2, basis="close", output=Path("output"), settings=None, indicator_settings=None, method=None, breakout_settings=None):
        """
        Build the desktop controls, chart canvas and swing-results table.

        No input data is loaded here. Export starts disabled and is enabled after a
        successful analysis. Detector settings are validated when results are refreshed.

        Args:
            root (tkinter.Tk): Existing Tk root window.
            window (int): Initial detector window shown in the controls; default is 2.
            basis (str): Initial price basis; default is 'close'.
            settings (TrendSettings or None): Initial trendline settings.
            indicator_settings (IndicatorSettings or None): Initial indicator periods/anchor.
            method (SwingMethod or None): Initial swing strategy; defaults to traditional TA.
            breakout_settings (BreakoutSettings or None): Initial Step 4 confirmation/follow-up rules.
            output (Path): Initial export-directory preference; default is Path("output").

        Result:
            None: Creates widgets and initializes empty data and analysis state.

        Exception:
            tkinter.TclError: If Tk cannot create or configure the interface.
        """
        # root: Tk root window owning the widgets and application event loop.
        # output: Preferred initial export directory; the user selects the actual destination.
        self.root, self.output = root, output
        # bars: All validated bars in chronological order; empty until a file is loaded.
        # source: Path of the loaded input file; None before a successful load.
        # current_run: Last successful plot snapshot (source, bars, points, window, basis, lines, settings, indicator_settings, method); None initially.
        self.bars, self.source, self.current_run = [], None, None
        # indicator_settings: Validated settings applied on the next successful refresh.
        self.indicator_settings = indicator_settings or IndicatorSettings()
        # indicator_result: Results for the last successful observed-prefix snapshot.
        self.indicator_result = None
        method = method or TraditionalTAMethod(TASettings(window, basis))
        # method_name: Selected strategy; changes apply only on a successful refresh.
        self.method_name = tk.StringVar(value=method.key)
        # method_settings: Immutable parameter objects retained separately for each strategy.
        self.method_settings = {name: cls().settings for name, cls in METHODS.items()}
        self.method_settings[method.key] = method.settings
        # breakout_settings: Validated rules; pending edits do not alter exported snapshots.
        self.breakout_settings = breakout_settings or BreakoutSettings()
        # breakout_snapshot: (events, settings) from the last successful refresh.
        self.breakout_snapshot = None
        root.title("SwingPoints | Steps 1-4 + Indicators")
        root.geometry("1350x950")
        controls = ttk.Frame(root, padding=8)
        controls.pack(fill="x")
        ttk.Button(controls, text="Open CSV / JSON", command=self.choose_file).pack(side="left", padx=4)
        # window: StringVar for neighbours on each side; converted to an integer on Apply.
        self.window = tk.StringVar(value=str(window if method.key == "ta" else 2))
        # basis: StringVar selecting "close" or "high-low" swing detection.
        self.basis = tk.StringVar(value=basis)
        # cutoff: StringVar for the number of observed bars (1..len(bars)), not an index.
        self.cutoff = tk.StringVar(value="1")
        self.ta_controls = []  # Widgets enabled only for the traditional TA strategy.
        for label, variable, choices in (("TA window", self.window, None), ("Swing basis", self.basis, ["close", "high-low"]),
                                         ("Observed bars", self.cutoff, None)):
            ttk.Label(controls, text=label).pack(side="left", padx=(12, 4))
            if choices:
                widget = ttk.Combobox(controls, textvariable=variable, values=choices, state="readonly", width=10)
                widget.pack(side="left")
            else:
                widget = ttk.Entry(controls, textvariable=variable, width=7)
                widget.pack(side="left")
            if variable is self.window or variable is self.basis:
                self.ta_controls.append(widget)
        ttk.Button(controls, text="Apply / replay", command=self.refresh).pack(side="left", padx=8)
        ttk.Button(controls, text="Next bar", command=self.next_bar).pack(side="left", padx=4)
        # export_button: Export button; disabled until a successful analysis is displayed.
        self.export_button = ttk.Button(controls, text="Export visible results", command=self.export, state="disabled")
        self.export_button.pack(side="left", padx=8)
        method_controls = ttk.Frame(root, padding=(12, 3))
        method_controls.pack(fill="x")
        ttk.Label(method_controls, text="Swing method").pack(side="left")
        selector = ttk.Combobox(method_controls, textvariable=self.method_name,
                               values=list(METHODS), state="readonly", width=15)
        selector.pack(side="left", padx=8)
        selector.bind("<<ComboboxSelected>>", self.method_changed)
        ttk.Button(method_controls, text="Method settings", command=self.edit_method_settings).pack(side="left", padx=4)
        self.method_description = tk.StringVar()
        ttk.Label(method_controls, textvariable=self.method_description).pack(side="left", padx=8)
        self.method_changed()
        settings = settings or TrendSettings()
        trend_controls = ttk.Frame(root, padding=(8, 2))
        trend_controls.pack(fill="x")
        # trend_tolerance: StringVar holding tolerance in percent of the first anchor price.
        self.trend_tolerance = tk.StringVar(value=str(settings.tolerance_percent))
        # trend_lookback: StringVar for the count of earlier same-kind anchor candidates.
        self.trend_lookback = tk.StringVar(value=str(settings.lookback))
        # min_touches: StringVar for the minimum confirmed touches required for display.
        self.min_touches = tk.StringVar(value=str(settings.min_touches))
        # max_lines: StringVar for the maximum displayed lines per direction.
        self.max_lines = tk.StringVar(value=str(settings.max_per_direction))
        for label, variable in (("Trend tolerance (%)", self.trend_tolerance),
                                ("Anchor lookback", self.trend_lookback),
                                ("Min touches", self.min_touches), ("Max lines / direction", self.max_lines)):
            ttk.Label(trend_controls, text=label).pack(side="left", padx=(8, 4))
            ttk.Entry(trend_controls, textvariable=variable, width=6).pack(side="left")
        ttk.Button(trend_controls, text="Indicator settings", command=self.edit_indicator_settings).pack(side="left", padx=8)
        ttk.Button(trend_controls, text="Indicator chart", command=self.show_indicators).pack(side="left", padx=4)
        breakout_controls = ttk.Frame(root, padding=(12, 3))
        breakout_controls.pack(fill="x")
        ttk.Button(breakout_controls, text="Step 4 settings", command=self.edit_breakout_settings).pack(side="left", padx=4)
        ttk.Button(breakout_controls, text="Breakout chart", command=self.show_breakouts).pack(side="left", padx=4)
        ttk.Label(breakout_controls, text="Close mode only | confirmation and false-break outcomes are separate").pack(side="left", padx=8)
        # status: StringVar bound to the status label showing the latest analysis summary.
        self.status = tk.StringVar(value="Open a CSV or JSON file. Window = bars on each side; all timestamps refer to completed bars.")
        ttk.Label(root, textvariable=self.status, padding=(12, 6)).pack(fill="x")
        # figure: Matplotlib Figure containing prices, swing markers and trendlines.
        self.figure = Figure(figsize=(12, 5.2))
        # canvas: FigureCanvasTkAgg that embeds the Matplotlib figure in the Tk window.
        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(self.canvas, root).update()
        notebook = ttk.Notebook(root)
        notebook.pack(fill="x", padx=10, pady=4)
        table_frame = ttk.Frame(notebook)
        notebook.add(table_frame, text="Confirmed swings")
        trend_frame = ttk.Frame(notebook)
        notebook.add(trend_frame, text="Displayed trendlines")
        trend_columns = ("line_id", "direction", "anchor1_bar", "anchor2_bar", "created_bar", "touch_count", "status", "broken_bar")
        # trend_table: Treeview listing selected displayed trendlines, not all exported candidates.
        self.trend_table = ttk.Treeview(trend_frame, columns=trend_columns, show="headings", height=7)
        for col in trend_columns:
            self.trend_table.heading(col, text=col.replace("_", " ").title())
            self.trend_table.column(col, width=130, anchor="center")
        trend_scrollbar = ttk.Scrollbar(trend_frame, orient="vertical", command=self.trend_table.yview)
        self.trend_table.configure(yscrollcommand=trend_scrollbar.set)
        self.trend_table.pack(side="left", fill="both", expand=True)
        trend_scrollbar.pack(side="right", fill="y")
        breakout_frame = ttk.Frame(notebook)
        notebook.add(breakout_frame, text="Step 4: all line events")
        breakout_columns = ("line_id", "direction", "candidate_bar", "confirmation_status", "confirmation_bar", "failure_bar", "deadline_bar", "outcome")
        # breakout_table: One row per line, including lines absent from the price chart.
        self.breakout_table = ttk.Treeview(breakout_frame, columns=breakout_columns, show="headings", height=7)
        for col in breakout_columns:
            self.breakout_table.heading(col, text=col.replace("_", " ").title())
            self.breakout_table.column(col, width=200 if col == "outcome" else 135, stretch=False, anchor="center")
        bx = ttk.Scrollbar(breakout_frame, orient="horizontal", command=self.breakout_table.xview)
        by = ttk.Scrollbar(breakout_frame, orient="vertical", command=self.breakout_table.yview)
        self.breakout_table.configure(xscrollcommand=bx.set, yscrollcommand=by.set)
        self.breakout_table.grid(row=0, column=0, sticky="nsew")
        bx.grid(row=1, column=0, sticky="ew")
        by.grid(row=0, column=1, sticky="ns")
        breakout_frame.columnconfigure(0, weight=1)
        breakout_frame.rowconfigure(0, weight=1)
        indicator_frame = ttk.Frame(notebook)
        notebook.add(indicator_frame, text="Indicators (blank = unavailable)")
        indicator_columns = ("bar", "timestamp", "sma", "ema", "rsi", "macd", "macd_signal",
                             "macd_histogram", "atr", "vwap", "roc", "cci", "vwap_status")
        # indicator_table: One row per observed bar; dates and missing-data status are explicit.
        self.indicator_table = ttk.Treeview(indicator_frame, columns=indicator_columns, show="headings", height=7)
        for col in indicator_columns:
            self.indicator_table.heading(col, text=col.replace("_", " ").upper())
            self.indicator_table.column(col, width=170 if col in ("timestamp", "vwap_status") else 100, stretch=False, anchor="center")
        hscroll = ttk.Scrollbar(indicator_frame, orient="horizontal", command=self.indicator_table.xview)
        vscroll = ttk.Scrollbar(indicator_frame, orient="vertical", command=self.indicator_table.yview)
        self.indicator_table.configure(xscrollcommand=hscroll.set, yscrollcommand=vscroll.set)
        self.indicator_table.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        indicator_frame.columnconfigure(0, weight=1)
        indicator_frame.rowconfigure(0, weight=1)
        columns = ("kind", "price", "pivot_bar", "pivot_time", "confirmed_bar", "confirmed_at")
        # table: Treeview listing confirmed swings and separate pivot/confirmation times.
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", height=7)
        for col in columns:
            self.table.heading(col, text=col.replace("_", " ").title())
            self.table.column(col, width=190 if "time" in col or "at" in col else 95, anchor="center")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def method_changed(self, event=None):
        """Enable applicable controls; leave the last plotted snapshot unchanged."""
        name = self.method_name.get()
        for widget in self.ta_controls:
            widget.configure(state=("readonly" if isinstance(widget, ttk.Combobox) else "normal")
                             if name == "ta" else "disabled")
        self.method_description.set(METHODS[name].label + " | " +
            ("Set window/basis above, then Apply / replay" if name == "ta" else
             "Close only; set parameters, then Apply / replay"))

    def selected_method(self):
        """Build the strategy selected by current controls, validating TA inputs."""
        name = self.method_name.get()
        settings = (TASettings(int(self.window.get()), self.basis.get()) if name == "ta"
                    else self.method_settings[name])
        return METHODS[name](settings)

    def edit_method_settings(self):
        """Edit only the selected method's dataclass attributes in a small dialog."""
        try:
            method = self.selected_method()
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        dialog = tk.Toplevel(self.root)
        dialog.title(method.label + " settings")
        variables = {}
        for row, field in enumerate(fields(method.settings)):
            ttk.Label(dialog, text=field.name.replace("_", " ").title()).grid(row=row, column=0, padx=12, pady=5)
            variable = tk.StringVar(value=str(getattr(method.settings, field.name)))
            variables[field.name] = variable
            if field.name == "basis":
                widget = ttk.Combobox(dialog, textvariable=variable, values=["close", "high-low"], state="readonly")
            else:
                widget = ttk.Entry(dialog, textvariable=variable)
            widget.grid(row=row, column=1, padx=12, pady=5)

        def apply():
            """Validate and store settings, then refresh the observed prefix."""
            try:
                values = {key: type(getattr(method.settings, key))(var.get()) for key, var in variables.items()}
                settings = method.settings_type(**values)
            except ValueError as exc:
                messagebox.showerror("Invalid method settings", str(exc), parent=dialog)
                return
            self.method_settings[method.key] = settings
            if method.key == "ta":
                self.window.set(str(settings.window))
                self.basis.set(settings.basis)
            dialog.destroy()
            if self.bars:
                self.refresh()
        ttk.Button(dialog, text="Apply", command=apply).grid(row=len(variables), column=0, columnspan=2, pady=12)

    def edit_breakout_settings(self):
        """Edit confirmation and follow-up counts and apply to the visible prefix."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Step 4 settings — completed observed bars")
        variables = {}
        for row, field in enumerate(fields(self.breakout_settings)):
            ttk.Label(dialog, text=field.name.replace("_", " ").title()).grid(row=row, column=0, padx=12, pady=5)
            variable = tk.StringVar(value=str(getattr(self.breakout_settings, field.name)))
            variables[field.name] = variable
            ttk.Entry(dialog, textvariable=variable).grid(row=row, column=1, padx=12)

        def apply():
            """Validate both counts before changing the applied rules."""
            try:
                settings = BreakoutSettings(**{name: int(v.get()) for name, v in variables.items()})
            except ValueError as exc:
                messagebox.showerror("Invalid Step 4 settings", str(exc), parent=dialog)
                return
            self.breakout_settings = settings
            dialog.destroy()
            if self.bars:
                self.refresh()
        ttk.Button(dialog, text="Apply", command=apply).grid(row=2, column=0, columnspan=2, pady=12)

    def show_breakouts(self):
        """Show events/settings from the last successful analysis, respecting replay."""
        if self.current_run is None or self.breakout_snapshot is None:
            messagebox.showinfo("Open data", "Load data and apply a valid run first.")
            return
        source, bars, _, _, basis, lines, trend_settings, _, _ = self.current_run
        events, settings = self.breakout_snapshot
        window = tk.Toplevel(self.root)
        window.title(f"Step 4 — {source.name} — {len(bars)} observed bars")
        window.geometry("1100x850")
        figure = Figure(figsize=(12, 9))
        draw_breakouts(figure, bars, events, lines, source.name, settings, trend_settings, basis)
        canvas = FigureCanvasTkAgg(figure, master=window)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(canvas, window).update()
        canvas.draw()

    def edit_indicator_settings(self):
        """Edit indicator class attributes; validate before applying to the visible prefix."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Indicator settings — periods count observed bars")
        variables = {}
        for row, field in enumerate(fields(self.indicator_settings)):
            ttk.Label(dialog, text=field.name.replace("_", " ").title()).grid(row=row, column=0, padx=12, pady=4, sticky="w")
            variable = tk.StringVar(value=str(getattr(self.indicator_settings, field.name)))
            variables[field.name] = variable
            if field.name == "vwap_reset":
                ttk.Combobox(dialog, textvariable=variable, values=["session", "cumulative"], state="readonly").grid(row=row, column=1, padx=12)
            else:
                ttk.Entry(dialog, textvariable=variable).grid(row=row, column=1, padx=12)

        def apply():
            """Commit valid settings; invalid input leaves existing settings untouched."""
            try:
                values = {key: variable.get() if key == "vwap_reset" else int(variable.get())
                          for key, variable in variables.items()}
                settings = IndicatorSettings(**values)
            except ValueError as exc:
                messagebox.showerror("Invalid indicator settings", str(exc), parent=dialog)
                return
            self.indicator_settings = settings
            dialog.destroy()
            if self.bars:
                self.refresh()
        ttk.Button(dialog, text="Apply", command=apply).grid(row=len(variables), column=0, columnspan=2, pady=12)

    def show_indicators(self):
        """Open the last successful run's indicator dashboard with zoom/save tools."""
        if self.current_run is None:
            messagebox.showinfo("Open data", "Load a file and apply a valid run first.")
            return
        source, bars, *_ = self.current_run
        window = tk.Toplevel(self.root)
        window.title(f"Indicators — {source.name} — {len(bars)} bars (snapshot)")
        window.geometry("1100x900")
        figure = Figure(figsize=(12, 11))
        draw_indicators(figure, bars, self.indicator_result, source.name)
        canvas = FigureCanvasTkAgg(figure, master=window)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(canvas, window).update()
        canvas.draw()

    def choose_file(self):
        """
        Open a file-selection dialog and load the selected price file.

        Args:
            None.

        Result:
            None: Loads the selected file; cancelling the dialog leaves the state unchanged.

        Exception:
            DataError from loading is handled by load() and displayed in a dialog.
            Tk dialog errors may propagate.
        """
        name = filedialog.askopenfilename(filetypes=[("Price data", "*.csv *.json"), ("All files", "*")])
        if name:
            self.load(Path(name))

    def load(self, path):
        """
        Load a price file and refresh the interface using all of its bars.

        Args:
            path (str or Path): Input CSV or JSON file to load.

        Result:
            None: On success, stores the bars and source path, resets export state,
                sets the observed-bar count and requests a chart/table refresh.

        Exception:
            DataError: Caught and displayed in a dialog; the existing data is retained.
            Unexpected GUI or plotting errors are not caught here.
        """
        try:
            bars = load_prices(path)
        except DataError as exc:
            messagebox.showerror("Cannot load data", str(exc))
            return
        self.bars, self.source = bars, Path(path)
        self.current_run = None
        self.breakout_snapshot = None
        self.export_button.configure(state="disabled")
        self.cutoff.set(str(len(bars)))
        self.refresh()

    def refresh(self):
        """
        Recalculate swings and trendlines for the selected observed-bar prefix.

        Reads settings from the interface. If no data has been loaded, an information
        dialog is shown. Only confirmed events within the selected prefix are displayed.

        Args:
            None.

        Result:
            None: On success, redraws the chart/table, records the current run,
                enables export and updates the status message.

        Exception:
            ValueError: Invalid window, basis or observed-bar count is caught and
                displayed in a dialog. Previously displayed results are retained.
            Unexpected plotting or GUI errors propagate.
        """
        if not self.bars:
            messagebox.showinfo("Open data", "Choose a CSV or JSON file first.")
            return
        try:
            method = self.selected_method()
            window, count = method.context_radius, int(self.cutoff.get())
            if not 1 <= count <= len(self.bars):
                raise ValueError(f"Observed bars must be between 1 and {len(self.bars)}.")
            visible = self.bars[:count]
            basis = method.basis
            settings = TrendSettings(float(self.trend_tolerance.get()), int(self.trend_lookback.get()),
                                     int(self.min_touches.get()), int(self.max_lines.get()))
            analysis = analyze(visible, method, settings, self.breakout_settings)
            points, lines = analysis.points, analysis.lines
            selected = select_trendlines(lines, settings)
            indicators = calculate_indicators(visible, self.indicator_settings)
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        draw_prices(self.figure, visible, points, window, basis, self.source.name, lines, settings, method=method)
        self.canvas.draw()
        self.table.delete(*self.table.get_children())
        for point in points:
            record = point.as_record()
            self.table.insert("", "end", values=[record[key] for key in self.table["columns"]])
        self.trend_table.delete(*self.trend_table.get_children())
        for line in selected:
            record = line.as_record(visible, True)
            self.trend_table.insert("", "end", values=[record[key] if record[key] is not None else ""
                                                      for key in self.trend_table["columns"]])
        self.breakout_table.delete(*self.breakout_table.get_children())
        for event in analysis.events:
            record = event.as_record(visible)
            self.breakout_table.insert("", "end", values=[record[k] if record[k] is not None else ""
                                                        for k in self.breakout_table["columns"]])
        self.breakout_snapshot = (analysis.events, analysis.breakout_settings)
        self.indicator_result = indicators
        self.indicator_table.delete(*self.indicator_table.get_children())
        for record in indicators.records(visible):
            self.indicator_table.insert("", "end", values=["" if record[key] is None else
                f"{record[key]:.6f}" if isinstance(record[key], float) else record[key]
                for key in self.indicator_table["columns"]])
        self.current_run = (self.source, visible, points, window, basis, lines, settings, self.indicator_settings, method)
        self.export_button.configure(state="normal")
        extra = " | Not enough history for this window" if window and count < 2*window+1 else ""
        if any((b.timestamp-a.timestamp).total_seconds() != 60 for a,b in zip(visible,visible[1:])):
            extra += " | Non-minute intervals present; windows count bars"
        if "missing_volume" in indicators.vwap_status:
            extra += " | VWAP: missing volume"
        extra += (f" | Step 4: {len(analysis.events)} line events" if basis == "close"
                  else " | Step 4 unavailable: use Close basis")
        self.status.set(f"{method.label} | {self.source.name} | {count}/{len(self.bars)} observed bars | {len(points)} confirmed swings | "
                        f"{len(selected)} displayed trendlines | Latest observed: {visible[-1].timestamp}{extra}")

    def next_bar(self):
        """
        Advance the replay cutoff by one bar and refresh the displayed results.

        Args:
            None.

        Result:
            None: Increases the observed count by one, capped at the loaded data length.

        Exception:
            ValueError: Missing data or an invalid count is caught and shown in a dialog.
            Other errors raised during refresh may propagate.
        """
        try:
            if not self.bars:
                raise ValueError("Open a price file first.")
            count = int(self.cutoff.get())
            if not 1 <= count <= len(self.bars):
                raise ValueError("Apply a valid observed-bar count first.")
            self.cutoff.set(str(min(count + 1, len(self.bars))))
            self.refresh()
        except ValueError as exc:
            messagebox.showerror("Cannot advance", str(exc))

    def export(self):
        """
        Ask for a destination and export the last successfully displayed analysis.

        Uses the stored current_run and displayed figure. Editing a control without
        applying it does not change the run being exported.

        Args:
            None.

        Result:
            None: Saves twelve result files and displays a success message. Does nothing
                when no run exists or the destination dialog is cancelled.

        Exception:
            OSError or ValueError: Export failures are caught and shown in a dialog.
            Other rendering or GUI errors may propagate.
        """
        if self.current_run is None:
            return
        folder = filedialog.askdirectory(title="Export the currently displayed run",
                                         initialdir=str(self.output if self.output.exists() else Path.cwd()))
        if not folder:
            return
        try:
            source, bars, points, window, basis, lines, settings, indicator_settings, method = self.current_run
            events, breakout_settings = self.breakout_snapshot
            export_results(folder, source, bars, points, window, basis, self.figure, lines, settings, indicator_settings,
                           method=method, breakout_settings=breakout_settings, events=events)
            messagebox.showinfo("Saved", f"Price/indicator/breakout charts, result tables and run summary saved to:\n{folder}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot export", str(exc))


def launch(path=None, window=2, basis="close", output=Path("output"), settings=None, indicator_settings=None, method=None, breakout_settings=None):
    """
    Create the desktop application and run its Tk event loop.

    Requires Tkinter, Matplotlib and an available graphical display. Input-data
    validation errors are displayed by the application instead of closing it.

    Args:
        path (str, Path or None): Optional price file to load immediately.
        window (int): Initial detector window; default is 2.
        basis (str): Initial price basis; default is 'close'.
        output (Path): Initial export-directory preference.
        settings (TrendSettings or None): Initial trendline settings.
        indicator_settings (IndicatorSettings or None): Initial indicator periods/anchor.
        method (SwingMethod or None): Initial swing strategy; defaults to traditional TA.
        breakout_settings (BreakoutSettings or None): Initial Step 4 confirmation/follow-up rules.

    Result:
        None: Returns after the Tk event loop ends, normally when the window closes.

    Exception:
        RuntimeError: If the initial Tk root cannot be created, such as when no
            graphical display is available. Later GUI errors may propagate.
    """
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("Tk could not open a display. Install Python with Tk or use CLI mode.") from exc
    app = SwingApp(root, window, basis, output, settings, indicator_settings, method=method, breakout_settings=breakout_settings)
    if path:
        app.load(path)
    root.mainloop()
