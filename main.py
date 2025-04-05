import re
import json
import datetime
import requests
from collections import defaultdict
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler
from fpdf import FPDF
from io import BytesIO
import pandas as pd
import os

ARQUIVO_JSON = "relatorio_dados.json"
TECNICOS_PRINCIPAIS = ["Gabriel", "Carlos", "Breno", "Wesley", "Daniel", "Phablo", "Lazaro"]
HF_TOKEN = os.getenv("HF_API_KEY")
HF_MODEL_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

def carregar_relatorio():
    try:
        with open(ARQUIVO_JSON, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def salvar_relatorio(data):
    with open(ARQUIVO_JSON, "w") as f:
        json.dump(data, f, indent=2)

relatorio_por_data = carregar_relatorio()

def analisar_com_huggingface(texto):
    if not texto or len(texto) < 30:
        print("⚠️ Texto muito curto, IA não será chamada.")
        return "erro"

    prompt = (
        "Leia o texto abaixo e diga se ele contém, de forma clara e direta:\n"
        "- Perda de garantia\n"
        "- Aprovação de orçamento\n"
        "- Reagendamento\n\n"
        "Apenas responda 'sim' para cada item se o texto AFIRMAR com clareza. Caso não haja menção clara, responda 'não'.\n"
        "Responda no formato:\n"
        "perda: sim/não, orçamento: sim/não, reagendamento: sim/não\n\n"
        f"Texto:\n{texto}"
    )
    try:
        response = requests.post(
            HF_MODEL_URL,
            headers=headers,
            json={"inputs": prompt},
            timeout=60
        )
        result = response.json()
        output = result[0]["generated_text"] if isinstance(result, list) else str(result)

        # Bloqueio de lixo/texto impróprio
        if any(word in output.lower() for word in ["porn", "xxx", "sex", "nude"]) or len(output) > 500:
            print("❌ Resposta ignorada por conteúdo suspeito.")
            return "erro"

        print("🔍 Análise da IA:", output)
        return output
    except Exception as e:
        print("❌ Erro ao chamar Hugging Face:", e)
        return "erro"

def interpretar_analise(analise, texto):
    texto = texto.lower()
    resposta = analise.lower()
    
    texto = texto.lower()
    resposta = analise.lower()

    # Verificações adicionais por palavras-chave simples
    if any(word in texto for word in ["orçamento aprovado", "orcamento aprovado", "foi aprovado", "cliente aprovou", "aprovado o orçamento", "orçamento aceito"]):
        resposta += " orçamento: sim"
    if any(word in texto for word in ["reagendado", "reagendado para", "nova visita", "remarcado", "foi reagendado", "mudança de data"]):
        resposta += " reagendamento: sim"
    if any(word in texto for word in ["perda de garantia", "uso incorreto", "garantia excluída", "exclusão de garantia", "sem garantia", "perdeu a garantia"]):
        resposta += " perda: sim"


        'perda_garantia': 'perda: sim' in resposta and 'garantia' in texto,
        'orc_aprovado': 'orçamento: sim' in resposta and ('aprov' in texto or 'orcamento' in texto),
        'reagendamento': 'reagendamento: sim' in resposta and 'reagend' in texto
    }

def extrair_dados(mensagem):
    dados = {}
    dados['tecnicos'] = re.findall(r'Tecnico: (.+?)\n', mensagem)
    dados['os'] = re.findall(r'OS:\s+(\d+)', mensagem)
    dados['data'] = re.findall(r'Data:\s+(\d+/\d+/\d+)', mensagem)
    dados['reparo'] = re.findall(r'Reparo:(.+?)\n', mensagem)
    dados['peca'] = re.findall(r'Peça:(.*)', mensagem)

    analise_ia = analisar_com_huggingface(mensagem)
    resultado = interpretar_analise(analise_ia, mensagem)
    dados.update(resultado)
    return dados

async def processar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    dados = extrair_dados(texto)

    data_msg = dados['data'][0] if dados['data'] else datetime.date.today().strftime('%d/%m/%Y')
    tecnicos_raw = dados['tecnicos'][0] if dados['tecnicos'] else ''
    tecnicos_encontrados = [nome.strip() for nome in re.split(r'[,/]', tecnicos_raw) if nome.strip()]
    tecnico_principal = next((nome.strip().capitalize() for nome in tecnicos_encontrados if nome.lower().strip() in [t.lower() for t in TECNICOS_PRINCIPAIS]), None)
    if not tecnico_principal:
        return

    relatorio = relatorio_por_data.setdefault(data_msg, {})
    tecnico_data = relatorio.setdefault(tecnico_principal, {'ordens': 0, 'orcamentos': 0, 'garantias': 0, 'reagendamentos': 0})
    tecnico_data['ordens'] += 1
    if dados['orc_aprovado']:
        tecnico_data['orcamentos'] += 1
    if dados['perda_garantia']:
        tecnico_data['garantias'] += 1
    if dados['reagendamento']:
        tecnico_data['reagendamentos'] += 1

    salvar_relatorio(relatorio_por_data)

async def gerar_relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    data = args[0] if args else datetime.date.today().strftime('%d/%m/%Y')
    relatorio = relatorio_por_data.get(data)
    if not relatorio:
        await update.message.reply_text(f"Nenhum atendimento registrado para {data}.")
        return

    texto = f"📅 Relatório - {data}\n\n"
    for tecnico, dados in relatorio.items():
        texto += f"👨‍🔧 {tecnico}\n"
        texto += f"• Ordens finalizadas: {dados['ordens']}\n"
        texto += f"• Orçamentos aprovados: {dados['orcamentos']}\n"
        texto += f"• Perdas de garantia: {dados['garantias']}\n"
        texto += f"• Reagendamentos: {dados['reagendamentos']}\n\n"
    await update.message.reply_text(texto)

async def exportar_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    data = args[0] if args else datetime.date.today().strftime('%d/%m/%Y')
    relatorio = relatorio_por_data.get(data)
    if not relatorio:
        await update.message.reply_text("Sem dados para exportar.")
        return

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Relatório - {data}", ln=True, align='C')
    pdf.ln(10)
    for tecnico, dados in relatorio.items():
        pdf.cell(200, 10, txt=f"{tecnico}", ln=True)
        pdf.cell(200, 10, txt=f"  Ordens: {dados['ordens']} | Orçamentos: {dados['orcamentos']} | Garantias: {dados['garantias']} | Reagendamentos: {dados['reagendamentos']}", ln=True)

    pdf_buffer = BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)
    await update.message.reply_document(document=pdf_buffer, filename=f"relatorio_{data.replace('/', '-')}.pdf")

async def exportar_xls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    data = args[0] if args else datetime.date.today().strftime('%d/%m/%Y')
    relatorio = relatorio_por_data.get(data)
    if not relatorio:
        await update.message.reply_text("Sem dados para exportar.")
        return

    df = pd.DataFrame.from_dict(relatorio, orient='index')
    df.index.name = "Técnico"
    buffer = BytesIO()
    df.to_excel(buffer, engine='openpyxl')
    buffer.seek(0)
    await update.message.reply_document(document=buffer, filename=f"relatorio_{data.replace('/', '-')}.xlsx")

if __name__ == '__main__':
    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), processar_mensagem))
    app.add_handler(CommandHandler("relatorio", gerar_relatorio))
    app.add_handler(CommandHandler("pdf", exportar_pdf))
    app.add_handler(CommandHandler("xls", exportar_xls))
    print("🚀 Bot seguro com IA filtrada e modelo Mistral iniciado.")
    app.run_polling()
