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
       ("Ella durmió", 0.09, 0.6, "cyan"),
        ("Al calor de las masas", 0.08, 1.2, "bold white"),
        ("Y yo desperté", 0.09, 0.5, "cyan"),
        ("Queriendo soñarla", 0.08, 1.2, "bold magenta"),
        ("Algún tiempo atrás", 0.07, 0.5, "yellow"),
        ("Pensé en escribirle", 0.07, 1.0, "bold white"),
        ("Que nunca sorteé", 0.08, 0.5, "green"),
        ("Las trampas del amor", 0.08, 1.5, "bold red")
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
#de cierta manera se necesitara la limpieza de puerto para poder disfrutar de una mejor experiencia

reproducir_tiktok()
#ademas de hacer la estructura entender el funcionamientpd del coodigp es de suma impirtancia parcialmente de esta manera se llegara a interpretar de la mejro aanerpa
