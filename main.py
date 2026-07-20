import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────
# CONFIGURAÇÕES GERAIS
# ─────────────────────────────────────────────

BASE_RPA_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_RPA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

ARQUIVO_LOG = LOG_DIR / f"rpa_fontes_dados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    filename=ARQUIVO_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)


# ─────────────────────────────────────────────
# LISTA DE SCRIPTS A EXECUTAR
# ─────────────────────────────────────────────

SCRIPTS = ["Insira os seu arquivos .py para atualização"]


# ─────────────────────────────────────────────
# FUNÇÃO PARA EXECUTAR CADA SCRIPT
# ─────────────────────────────────────────────

def executar_script(script_info):
    nome_script = script_info["name"]
    diretorio = Path(script_info["directory"])
    descricao = script_info["description"]

    caminho_script = diretorio / nome_script

    print("\n" + "-" * 80)
    print(f"Processo: {descricao}")
    print(f"Script: {caminho_script}")
    print("-" * 80)

    logging.info("-" * 80)
    logging.info(f"Iniciando processo: {descricao}")
    logging.info(f"Script: {caminho_script}")

    if not diretorio.exists():
        mensagem = f"Diretório não encontrado: {diretorio}"
        print(f"ERRO: {mensagem}")
        logging.error(mensagem)
        return False

    if not caminho_script.exists():
        mensagem = f"Script não encontrado: {caminho_script}"
        print(f"ERRO: {mensagem}")
        logging.error(mensagem)
        return False

    inicio = datetime.now()

    try:
        resultado = subprocess.run(
            [sys.executable, str(caminho_script)],
            cwd=str(diretorio),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        fim = datetime.now()
        duracao = fim - inicio

        if resultado.returncode == 0:
            print(f"Concluído com sucesso: {descricao}")
            print(f"Tempo de execução: {duracao}")

            logging.info(f"Concluído com sucesso: {descricao}")
            logging.info(f"Tempo de execução: {duracao}")

            if resultado.stdout:
                logging.info(f"STDOUT:\n{resultado.stdout}")

            return True

        else:
            print(f"ERRO ao executar: {descricao}")
            print(f"Código de retorno: {resultado.returncode}")
            print(f"Tempo até o erro: {duracao}")

            if resultado.stderr:
                print("\nDetalhe do erro:")
                print(resultado.stderr)

            logging.error(f"Erro ao executar: {descricao}")
            logging.error(f"Código de retorno: {resultado.returncode}")
            logging.error(f"Tempo até o erro: {duracao}")
            logging.error(f"STDOUT:\n{resultado.stdout}")
            logging.error(f"STDERR:\n{resultado.stderr}")

            return False

    except Exception as e:
        print(f"Falha inesperada ao executar {descricao}: {e}")
        logging.exception(f"Falha inesperada ao executar {descricao}: {e}")
        return False


# ─────────────────────────────────────────────
# EXECUÇÃO PRINCIPAL DO RPA
# ─────────────────────────────────────────────

def main():
    print("=" * 80)
    print("INÍCIO DO RPA DE ATUALIZAÇÃO DAS FONTES DE DADOS")
    print("=" * 80)
    print(f"Log da execução: {ARQUIVO_LOG}")

    logging.info("=" * 80)
    logging.info("INÍCIO DO RPA DE ATUALIZAÇÃO DAS FONTES DE DADOS")
    logging.info("=" * 80)

    inicio_geral = datetime.now()

    total_scripts = len(SCRIPTS)
    scripts_executados = 0

    for indice, script_info in enumerate(SCRIPTS, start=1):
        print(f"\nExecutando {indice}/{total_scripts}")

        sucesso = executar_script(script_info)

        if not sucesso:
            logging.error(f"Rotina interrompida no processo {indice}/{total_scripts}: {script_info['description']}")

            print("\n" + "=" * 80)
            print("RPA INTERROMPIDO COM ERRO")
            print("=" * 80)
            print(f"Processo com erro: {script_info['description']}")
            print(f"Script: {script_info['name']}")
            print(f"Verifique o log em: {ARQUIVO_LOG}")

            sys.exit(1)

        scripts_executados += 1

    fim_geral = datetime.now()
    duracao_geral = fim_geral - inicio_geral

    logging.info("=" * 80)
    logging.info("RPA FINALIZADO COM SUCESSO")
    logging.info(f"Scripts executados: {scripts_executados}/{total_scripts}")
    logging.info(f"Tempo total de execução: {duracao_geral}")
    logging.info("=" * 80)

    print("\n" + "=" * 80)
    print("RPA FINALIZADO COM SUCESSO")
    print("=" * 80)
    print(f"Scripts executados: {scripts_executados}/{total_scripts}")
    print(f"Tempo total de execução: {duracao_geral}")
    print(f"Log salvo em: {ARQUIVO_LOG}")


if __name__ == "__main__":
    main()
