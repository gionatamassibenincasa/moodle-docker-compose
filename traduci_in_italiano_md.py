import argparse
import os
import sys
import marko
from marko.md_renderer import MarkdownRenderer
from ollama import chat

# --- CONFIGURAZIONE ---
DEFAULT_MODEL = "qwen2.5:3b" 

SYSTEM_PROMPT = """
Sei un traduttore tecnico. Traduci il frammento Markdown dall'Inglese all'Italiano.
1. Mantieni INTATTA la sintassi Markdown interna (es. **grassetto**, [link](url), `codice inline`).
2. NON tradurre termini tecnici (es. framework, pipeline, deploy, loop).
3. NON tradurre URL o percorsi file.
4. Restituisci SOLO la stringa tradotta.
"""

def parse_arguments():
    parser = argparse.ArgumentParser(description="Traduttore Markdown AST per RPi5.")
    parser.add_argument("filename", help="File Markdown sorgente (.md)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Modello (default: {DEFAULT_MODEL})")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode")
    return parser.parse_args()

def translate_text(text, model):
    """Invia testo a Ollama."""
    if not text.strip(): 
        return text
    try:
        response = chat(model=model, messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': text},
        ])
        return response['message']['content']
    except Exception as e:
        sys.stderr.write(f"[ERRORE API] {e}\n")
        return text # Fallback: restituisce originale se fallisce

def process_markdown_ast(input_path, output_path, model, verbose):
    # 1. Parsing dell'intero documento in un AST
    with open(input_path, "r", encoding="utf-8") as f:
        text_content = f.read()
    
    document = marko.parse(text_content)
    
    # Instanziamo il renderer Markdown di Marko per riconvertire i singoli nodi in testo
    renderer = MarkdownRenderer()
    
    total_nodes = len(document.children)
    print(f"--- Analisi completata: {total_nodes} blocchi strutturali individuati ---")
    
    with open(output_path, "w", encoding="utf-8") as out_f:
        # 2. Iterazione sui nodi di primo livello (Streaming Processing)
        for i, node in enumerate(document.children):
            
            # Renderizziamo il nodo corrente in stringa Markdown originale
            # Questo gestisce automaticamente la ricorsione interna (es. grassetto dentro un paragrafo)
            original_segment = renderer.render(node)
            
            # Identifichiamo il tipo di nodo
            node_type = type(node).__name__
            
            # Lista dei nodi da NON tradurre (Codice, HTML grezzo)
            # FencedCode è il blocco ``` ... ```
            # CodeBlock è il blocco indentato con 4 spazi
            skip_translation = node_type in ["FencedCode", "CodeBlock", "HTMLBlock", "ThematicBreak", "BlankLine"]
            
            final_segment = ""
            
            print(f"\r[{i+1}/{total_nodes}] Elaborazione {node_type}...", end='', flush=True)

            if skip_translation:
                if verbose:
                    sys.stderr.write(f"\n[SKIP] {node_type}\n")
                final_segment = original_segment
            else:
                # È un nodo di testo (Paragraph, Heading, Quote, List)
                # Nota: Se è una lista lunga, verrà tradotta tutta insieme per mantenere il contesto.
                # Se preferisci spezzare anche le liste item per item, servirebbe una ricorsione più profonda,
                # ma per le guide IT solitamente tradurre la lista intera è meglio per la coerenza.
                
                if verbose:
                    sys.stderr.write(f"\n--- [IN] ---\n{original_segment.strip()}\n")
                
                # Traduzione
                translated_text = translate_text(original_segment, model)
                
                # Pulizia: A volte gli LLM mangiano il newline finale richiesto dal markdown
                if original_segment.endswith('\n') and not translated_text.endswith('\n'):
                    translated_text += '\n'
                
                if verbose:
                    sys.stderr.write(f"--- [OUT] ---\n{translated_text.strip()}\n")
                
                final_segment = translated_text

            # 3. Scrittura immediata (Incremental Flush)
            out_f.write(final_segment)
            out_f.flush()
            os.fsync(out_f.fileno())

    print(f"\n\n--- COMPLETATO --- File salvato in: {output_path}")

def main():
    args = parse_arguments()
    if not os.path.exists(args.filename):
        sys.exit("File non trovato.")
        
    base, ext = os.path.splitext(args.filename)
    output_file = f"{base}_it{ext}"
    
    process_markdown_ast(args.filename, output_file, args.model, args.verbose)

if __name__ == "__main__":
    main()