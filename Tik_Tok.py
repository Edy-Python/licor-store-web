import time
import os
import sys  # Importamos esto para forzar a la terminal a ser rápida
from rich.console import Console

# Iniciamos nuestra consola "rich"
consola = Console()

def limpiar_pantalla():
    os.system('cls' if os.name == 'nt' else 'clear')

def reproducir_tiktok():
    cancion = [
        ("Yo...", 0.3, 0.7, "bold cyan"),
        ("Quise encontrar...", 0.09, 1.5, "bold cyan"),
        ("Un gran cariño", 0.09, 0.6, "bold cyan"),
        ("Y no lo pude hallar", 0.09, 2.0, "bold cyan"),
        ("Sí...", 0.2, 1.2, "bold cyan"),
        ("Tanto busqué", 0.09, 2.4, "bold cyan"),
        ("Y al fin en mi camino te encontre", 0.09, 3.0, "bold cyan"),
        ("Leydi...", 0.09, 1.8, "bold red"),
        ("Cielo azul", 0.09, 1.9, "bold blue"),
        ("Sol de las mañanas", 0.1, 1.0, "bold yellow"),
        ("Mi alegria de vivir", 0.09, 1.9, "bold white"),
        ("Leydi...", 0.09, 1.0, "bold red"),
        ("Suave tu piel", 0.09, 2.5, "bold cyan"),
        ("Tus ojos", 0.09, 1.0, "bold yellow"),
        ("Tu sonrisa", 0.09, 1.0, "bold white"),
        ("Me enseñaron a querer...", 0.09, 1.0, "bold cyan"),
        ("Leydi... mi amor...", 0.09, 3.8, "bold cyan"),
        ("Leydi... mi amor....", 0.2, 0.03,"bold blue")
    ]

    limpiar_pantalla()

    print("\n\n") 

    for frase, velocidad_letra, pausa_final, color in cancion:
        for letra in frase:
            
            consola.print(letra, style=color, end="")
            
          
            sys.stdout.flush()
            time.sleep(velocidad_letra)
            
        print() 
        time.sleep(pausa_final) 


reproducir_tiktok()