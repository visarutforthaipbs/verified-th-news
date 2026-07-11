from deep_translator import GoogleTranslator

try:
    translated = GoogleTranslator(source='en', target='th').translate("One of the delicious snacks is roti")
    print(f"Translated: {translated}")
except Exception as e:
    print(f"Error: {e}")
