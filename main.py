from dotenv import load_dotenv

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Button, DataTable
from textual.screen import Screen
from textual import on
from datetime import datetime

import typer

load_dotenv()

app = typer.Typer()

class Dashboard(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        with Container():
            yield Static(f"Dashboard - {datetime.now().strftime('%Y-%m-%d %H:%M')}", classes="title")

            with Horizontal():
                yield Static("Open Invoices\n[bold red]12[/]", classes="metric")
                yield Static("Paid Invoices\n[bold green]47[/]", classes="metric")
                yield Static("Earned (12m)\n[bold green]$184,230[/]", classes="metric")
                yield Static("Expenses (12m)\n[bold red]$63,450[/]", classes="metric")

            yield Static("\nPress 'i' for Invoices, 't' for Timesheets, 'q' to quit", classes="hint")

class InvoicesScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Static("📋 Invoices", classes="title")

        table = DataTable()
        table.add_columns("ID", "Client", "Amount", "Status", "Due Date")
        table.add_rows([
            ("INV-001", "Acme Corp", "$2,400", "Open", "2026-06-15"),
            ("INV-002", "Stark Industries", "$8,750", "Paid", "2026-05-20"),
            # ... more rows
        ])
        yield table

        yield Button("Back to Dashboard", id="back")

class TimesheetsScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Static("⏱️ Timesheets", classes="title")

        table = DataTable()
        table.add_columns("ID", "Client", "Amount", "Status", "Due Date")
        table.add_rows([
            ("INV-001", "Acme Corp", "$2,400", "Open", "2026-06-15"),
            ("INV-002", "Stark Industries", "$8,750", "Paid", "2026-05-20"),
            # ... more rows
        ])
        yield table

        yield Button("Back to Dashboard", id="back")


class MainApp(App):
    CSS_PATH = "app.tcss"  # optional styling

    # Register screens by name so key bindings work
    SCREENS = {
        "dashboard": Dashboard,
        "invoices": InvoicesScreen,
        "timesheets": TimesheetsScreen,
    }

    BINDINGS = [
        ("d", "switch_mode('dashboard')", "Dashboard"),
        ("i", "push_screen('invoices')", "Invoices"),
        ("t", "push_screen('timesheets')", "Timesheets"),
        ("q", "quit", "Quit"),
    ]

    def on_mount(self) -> None:
        self.push_screen(Dashboard())

    def action_switch_mode(self, mode: str):
        if mode == "dashboard":
            self.push_screen(Dashboard())
        elif mode == "invoices":
            self.push_screen(InvoicesScreen())
        elif mode == "timesheets":
            self.push_screen(TimesheetsScreen())

    @on(Button.Pressed, "#back")
    def back_to_dashboard(self):
        self.pop_screen()


if __name__ == "__main__":
    app = MainApp()
    app.run()
