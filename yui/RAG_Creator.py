from langchain_text_splitters import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)
import os

try:
    import ollama
except ImportError:
    raise ImportError("Installiere zuerst das Paket mit: pip install ollama")

try:
    import psycopg2
except ImportError:
    raise ImportError("Installiere zuerst das Paket mit: pip install psycopg2")


try:

    connection = psycopg2.connect(
    host="localhost",          # Auf dem Server ist die Datenbank 'local'
    database="rag_datenbank",
    user="postgres",
    password=os.getenv("EVA_PASSWORD"),
    port="5432"                # Der Standard-Postgres-Port auf dem Server
)

    cursor = connection.cursor()
except psycopg2.Error as e:
    print("Fehler beim Verbinden mit der Datenbank:", e)
    exit(1)

with open("yui/test.txt", "r", encoding="utf-8") as f:
    text = f.read()



def generate_embeddings():


    response = ollama.embed(
        model="bge-m3",
        input=text
    )
    return response["embeddings"] [0]

result = generate_embeddings()
print("Embeddings generiert:", result)

postgres_insert_query = """
INSERT INTO eva_knowledge (text_section, embedding) VALUES (%s, %s)
"""
record_to_insert = (text, result)

cursor.execute(postgres_insert_query, record_to_insert)
connection.commit()
print("Daten erfolgreich in die Datenbank eingefügt.")

if "connection" in locals():
    if connection:
        cursor.close()
        connection.close()