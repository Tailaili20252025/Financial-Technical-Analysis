"""Optional Tkinter interface; the core program also runs without a display."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from .data import DataError, load_prices
from .detector import detect_swings
from .output import export_results
from .plotting import draw_prices


class SwingApp:
    """File picker, configurable detector, historical cutoff, chart and table."""

    def __init__(self, root, window=2, basis="close", output=Path("output")):
        """
        Build the desktop controls, chart canvas and swing-results table.

        No input data is loaded here. Export starts disabled and is enabled after a
        successful analysis. Detector settings are validated when results are refreshed.

        Args:
            root (tkinter.Tk): Existing Tk root window.
            window (int): Initial detector window shown in the controls; default is 2.
            basis (str): Initial price basis; default is 'close'.
            output (Path): Initial export-directory preference; default is Path("output").

        Result:
            None: Creates widgets and initializes empty data and analysis state.

        Exception:
            tkinter.TclError: If Tk cannot create or configure the interface.
        """
        self.root, self.output = root, output
        self.bars, self.source, self.current_run = [], None, None
        root.title("SwingPoints | Steps 1-2")
        root.geometry("1250x850")
        controls = ttk.Frame(root, padding=8)
        controls.pack(fill="x")
        ttk.Button(controls, text="Open CSV / JSON", command=self.choose_file).pack(side="left", padx=4)
        self.window = tk.StringVar(value=str(window))
        self.basis = tk.StringVar(value=basis)
        self.cutoff = tk.StringVar(value="1")
        for label, variable, choices in (("Window", self.window, None), ("Swing basis", self.basis, ["close", "high-low"]),
                                         ("Observed bars", self.cutoff, None)):
            ttk.Label(controls, text=label).pack(side="left", padx=(12, 4))
            if choices:
                ttk.Combobox(controls, textvariable=variable, values=choices, state="readonly", width=10).pack(side="left")
            else:
                ttk.Entry(controls, textvariable=variable, width=7).pack(side="left")
        ttk.Button(controls, text="Apply / replay", command=self.refresh).pack(side="left", padx=8)
        ttk.Button(controls, text="Next bar", command=self.next_bar).pack(side="left", padx=4)
        self.export_button = ttk.Button(controls, text="Export visible results", command=self.export, state="disabled")
        self.export_button.pack(side="left", padx=8)
        self.status = tk.StringVar(value="Open a CSV or JSON file. Window = bars on each side; all timestamps refer to completed bars.")
        ttk.Label(root, textvariable=self.status, padding=(12, 6)).pack(fill="x")
        self.figure = Figure(figsize=(12, 5.2))
        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(self.canvas, root).update()
        table_frame = ttk.Frame(root, padding=(10, 4))
        table_frame.pack(fill="x")
        columns = ("kind", "price", "pivot_bar", "pivot_time", "confirmed_bar", "confirmed_at")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", height=7)
        for col in columns:
            self.table.heading(col, text=col.replace("_", " ").title())
            self.table.column(col, width=190 if "time" in col or "at" in col else 95, anchor="center")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

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
        self.export_button.configure(state="disabled")
        self.cutoff.set(str(len(bars)))
        self.refresh()

    def refresh(self):
        """
        Recalculate and display swings for the selected observed-bar prefix.

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
            window, count = int(self.window.get()), int(self.cutoff.get())
            if not 1 <= count <= len(self.bars):
                raise ValueError(f"Observed bars must be between 1 and {len(self.bars)}.")
            visible = self.bars[:count]
            basis = self.basis.get()
            points = detect_swings(visible, window, basis)
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        draw_prices(self.figure, visible, points, window, basis, self.source.name)
        self.canvas.draw()
        self.table.delete(*self.table.get_children())
        for point in points:
            record = point.as_record()
            self.table.insert("", "end", values=[record[key] for key in self.table["columns"]])
        self.current_run = (self.source, visible, points, window, basis)
        self.export_button.configure(state="normal")
        extra = " | Not enough history for this window" if count < 2*window+1 else ""
        if any((b.timestamp-a.timestamp).total_seconds() != 60 for a,b in zip(visible,visible[1:])):
            extra += " | Non-minute intervals present; windows count bars"
        self.status.set(f"{self.source.name} | {count}/{len(self.bars)} observed bars | {len(points)} confirmed swings | "
                        f"Latest observed: {visible[-1].timestamp}{extra}")

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
            None: Saves four result files and displays a success message. Does nothing
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
            source, bars, points, window, basis = self.current_run
            export_results(folder, source, bars, points, window, basis, self.figure)
            messagebox.showinfo("Saved", f"Chart, swing table and run summary saved to:\n{folder}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot export", str(exc))


def launch(path=None, window=2, basis="close", output=Path("output")):
    """
    Create the desktop application and run its Tk event loop.

    Requires Tkinter, Matplotlib and an available graphical display. Input-data
    validation errors are displayed by the application instead of closing it.

    Args:
        path (str, Path or None): Optional price file to load immediately.
        window (int): Initial detector window; default is 2.
        basis (str): Initial price basis; default is 'close'.
        output (Path): Initial export-directory preference.

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
    app = SwingApp(root, window, basis, output)
    if path:
        app.load(path)
    root.mainloop()
