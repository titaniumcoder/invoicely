import typer
from rich import rprint

from dotenv import load_dotenv

app = typer.Typer()
load_dotenv()

@app.command()
def hello(name: str):
    rprint(f"[italic red]Hello[/italic red] {name}!", locals())

@app.command()
def goodbye(name: str, formal: bool = False):
    if formal:
        print(f"Goodbye Mr. {name}. Have a good day.")
    else:
        print(f"Bye {name}!")

if __name__ == "__main__":
    app()
