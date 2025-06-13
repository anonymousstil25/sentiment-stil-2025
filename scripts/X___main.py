from openai import OpenAI
import time
import pandas as pd
import re, json, ast, os


path_run_code = ""
chatgpt_key = ""

def extract_sentiment(text):
    if not isinstance(text, str):
        return None

    text = text.strip()
    if not text:
        return None

    if 'sentiment' not in text.lower():
        return None

    # TODO: Lembrar de passar a função novamente em todos os modelos por conta disto!!!!
    pattern = r'python\s*(\{.*?\})\s*|(\{.*?\})'
    matches = re.findall(pattern, text, flags=re.DOTALL)

    extracted = []
    for py_block, json_block in matches:
        candidate = py_block or json_block 
        candidate = candidate.strip()

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                data = ast.literal_eval(candidate)
            except (ValueError, SyntaxError):
                continue

        if isinstance(data, dict) and 'sentiment' in data:
            extracted.append(data['sentiment'])

    if len(extracted) >= 2: 
        return extracted[len(extracted) - 1]
    
    if not extracted:
        return None
    
    return extracted[0] if type(extracted) is list else extracted

llms = (
    "gpt-4o", 
    "gpt-4o-mini",
    "deepseek-r1-distill-llama-70b",
    "deepseek-r1-distill-qwen-32b", 
    "deepseek-r1-distill-qwen-14b", 
    "deepseek-r1-distill-llama-8b",
    "deepseek-r1-distill-qwen-1.5b",
    "gemma-3-27b-it",
    "gemma-3-12b-it",
    "gemma-3-4b-it",
    "gemma-3-1b-it",
    "llama-3.3-70b-instruct",
    "meta-llama-3-8b-instruct",
    "llama-3.2-3b-instruct",
    "llama-3.2-1b-instruct",
    "qwen3-32b",
    "qwen3-30b-a3b", 
    "qwen3-14b",
    "qwen3-8b",
    "qwen3-1.7b",
    "qwen3-0.6b",
    "phi-4",
    "phi-4-mini-instruct",
    "zephyr-7b-beta",
    "stablelm-zephyr-3b",
    "stablelm-2-zephyr-1_6b",
    "mistral-small-3.1-24b-instruct-2503",
    "mistral-7b-instr?uct-v0.3"
)

llms_no_user_template = ("mistral-7b-instruct-v0.3")

tp_prompts = ["ZS", "FS", "CoT", "CoT_FS"]

for tp_prompt in tp_prompts:

    # Load the CSV file
    csv_path = ''
    dataset_name = f'dataset_{tp_prompt}.csv'
    df = None
    if os.path.exists(csv_path+dataset_name):
        df = pd.read_csv(csv_path+dataset_name, delimiter=';')
    else:
        dataset_name = 'dataset.csv'
        df = pd.read_csv(csv_path+dataset_name, delimiter=';')

    for llm_name in llms:       

        if llm_name in df.columns:
            print(f"{llm_name} já rodou para o prompt {tp_prompt}")
            continue

        # Point to the local server
        client = None
        if llm_name == 'gpt-4o' or llm_name == 'gpt-4o-mini':
            client = OpenAI(api_key=chatgpt_key)
        else:
            client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
        
        with open(f"prompts/{tp_prompt}.txt", 'r', encoding='utf-8') as arquivo:
            content_prompt = arquivo.read()

        system_message = content_prompt
        # Create a new column for the LLM's predictions
        column_name = llm_name
        df[column_name] = ""
        df[column_name+"_response"] = ""

        # Variáveis para contagem de acertos e erros
        correct_predictions = 0
        total_predictions = 0


        # Iterate through each row of the CSV
        for index, row in df.iterrows():
            user_message = f"""
                User text: {row['content']}
                Response:
            """

            start_time = time.time()

            messages = None
            if llm_name in llms_no_user_template:
                messages=[                    
                    {"role": "user", "content": system_message+"\n"+user_message}
                ]
            else:
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ]
            
            # Adicione estas variáveis antes do loop (opcional, para clareza)
            max_retries = 3

            # Dentro do seu loop "for index, row in df.iterrows():" faça isso:
            attempt = 0
            while attempt <= max_retries:
                try:
                    completion = client.chat.completions.create(
                        model=column_name,
                        messages=messages,
                        temperature=0.0,  # Setting temperature to 0 for more deterministic output
                        max_completion_tokens=1000
                    )
                    break
                except Exception as e:
                    attempt += 1
                    print(f"Tentativa {attempt}/{max_retries} ({llm_name}) falhou com erro: {e}")
                    if attempt > max_retries:
                        print(f"Inferência falhou após {max_retries} tentativas. Encerrando execução.")
                        raise 
                    else:
                        print("Aguardando 5 segundos antes de tentar novamente.")
                        time.sleep(5)

                        
            end_time = time.time()
            duration = end_time - start_time
            # print("========================================")
            # print("=============== LLM ===============")
            # print(f"")
            # print()
            predicted_module = extract_sentiment(completion.choices[0].message.content)
            print(f"🎲 Dataset: {row['sentiment']}")
            print(f"🤖 IA     : {predicted_module[0] if type(predicted_module) == list else predicted_module}")
            print()
            try:
                df.loc[index, column_name] = predicted_module[0] if type(predicted_module) is list else predicted_module
                df.loc[index, column_name+"_response"] = completion.choices[0].message.content
                df.loc[index, column_name+"_time"] = duration
                df.loc[index, column_name+"_n_tokens_in"] = completion.usage.prompt_tokens
                df.loc[index, column_name+"_n_tokens_out"] = completion.usage.completion_tokens
            except Exception as ex:
                print(ex)
                continue
            
            print(f"[{llm_name}/{tp_prompt}] {index + 1} of {len(df)}")
            print("========================================")


        # Calculate accuracy
        correct_predictions = (df["sentiment"] == df[column_name]).sum()
        total_examples = len(df)
        accuracy = correct_predictions / total_examples if total_examples > 0 else 0 # Avoid division by 0
        print(f"Accuracy {llm_name} [{tp_prompt}]: {accuracy:.2%}")

        # Save the updated CSV
        dataset_name = f'dataset_{tp_prompt}.csv'
        df.to_csv(csv_path+dataset_name, index=False, sep=";")