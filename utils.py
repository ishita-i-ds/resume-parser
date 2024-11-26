import os, re, json, io
from io import StringIO
from pathlib import Path
import pdfplumber
import docx2txt
import pandas as pd
import streamlit as st
import openai
from openai import AzureOpenAI
import datetime
from dotenv import load_dotenv
import time

load_dotenv()

deployement_name=os.getenv("deployement_name")
api_type=os.getenv("api_type")
api_base=os.getenv("api_base")
api_version=os.getenv("api_version")
api_key=os.getenv("api_key")
model=os.getenv("model")

# Configure OpenAI API
openai.api_type = api_type
openai.api_base = api_base
openai.api_version = api_version
openai.api_key = api_key

from openai import OpenAI
 
# Point to the local server

def color_selection(val):
    color = 'green' if val=='Strong Match' else 'yellow' if val=='Potential Match' else 'red' 
    return f'color: {color}'

@st.cache_data
def get_openai_response(input_prompt):
    AzureOpenAIclient = AzureOpenAI(
        azure_endpoint=openai.api_base,
        api_key=openai.api_key,
        api_version=openai.api_version,
        azure_deployment=deployement_name
    )
    # client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
    # llm="lmstudio-community/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
    messages=[
        {"role": "system", "content": "You are a skilled ATS (Application Tracking System) with a deep understanding of tech fields, software engineering, data science, data analysis, and big data. You provide the best assistance for resume selection based on job descriptions."},
        {"role": "user", "content": input_prompt}
    ]
    
    # insight_text = client.chat.completions.create(
    insight_text = AzureOpenAIclient.chat.completions.create(
        messages=messages,
        model=llm,
        temperature=0,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
    )
    print(insight_text.choices[0].message)
    #return insight_text.choices[0].message
    return insight_text.choices[0].message.content

@st.cache_data
def extract_pdf_text(uploaded_file):
    with pdfplumber.open(uploaded_file) as pdf:
        text_data = []
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            paragraphs = re.split(r'\n\s*\n', text)   ###re???
            text_data.append({"page_number": page_num + 1, "paragraphs": paragraphs})
    return text_data


@st.cache_data
def extract_docx_text(uploaded_file):
    text=docx2txt.process(uploaded_file)
    paragraphs=text.split('\n\n')
    text_data=[{'paragraphs':paragraphs}]
    return text_data

@st.cache_data
def process_resume(resume_files, jd, additional_inputs):
    print('Extracting Information from Resume')
    results = []


    first_prompt = f"""
    **Objective:** conversion of Job description to checklist for Resume shortlisting
    **Input:** The input is a job description in text format: {jd}
    **Steps:** Look for critical asks and make sure they are part of the checklist
    **Output:** the Job Description should be converted to a Selection checklist in the form of JSON.
    """
    jd_json  = get_openai_response(first_prompt)


    for files in resume_files:
        ext = Path(files.name).suffix
        print(ext)
        ext = Path(files.name).suffix.lower()
        print(ext)
        if ext == ".pdf":
            #text_bytes=StringIO(files.getvalue().decode("utf-8"))
            resume_text = extract_pdf_text(files)
        elif ext == ".docx":
            resume_text = extract_docx_text(files)
        #elif ext == ".doc":
            #resume_text = extract_doc_text(files)
        else:
            raise ValueError("Unsopported file type: {}".format(ext))

    paragraphs = []
    for page_data in resume_text:
        paragraphs.extend(page_data["paragraphs"])

    second_prompt = """
    **Objective:** conversion of resume to a JSON with essential details 
    **Input:** The input is a detailed resume: {0}
    **Steps:** Look for details like Project, skills, experience etc and make sure they are part of the output created as json
    **Output:** the detailed resume should be converted to a JSON which has all relevant details required for shortlisting, Critical skills, experiences, etc
    """.format('\n'.join(paragraphs))
    resume_json  = get_openai_response(second_prompt)
    
    third_prompt = f"""
    Evaluate and be accurate in selection of the following resume based on the given job description checklist and additional input.
    
    **Objective:** Accurate Resume shortlisting 
    
    **Focus:** You need to look at the Job description Checklist and the Resume to arrive at the final decision
    
    **Selection:** You cannot go wrong, evaluate resume for each critical skill mentioned in Job description to arrive at the final decision
    
    **You need to provide 3 reasons for your selection decision
     **Primary Skills: Identify the primary skills of the candidate from his profile/resume.
     **Secondary Skills: Identify the secondary skills of the candidate from his profile/resume.
     **Entity Recognition: Identify Personally Identifiable information of the candidate, specifically Name, email and phone number if available. Do not make these up if unavailable.
     
     **Output:**
     * **Score:** Percentage of "must-have" skills matched (float)
     * **Name:** Name of the candidate ({files.name})
     * **Contact:** Contact Details of the candidate.
     * **Primary Skills: Primary skills of the candidate separated by commas.
     * **Secondary Skills: Secondary skills of the candidate separated by commas.
     **Selection:** Categorize the candidate as "Strong Match," "Potential Match," or "Not a Match" based on the following criteria:
     
        * **Strong Match:** Meets or exceeds all critical skills and most preferred skills. 
        * **Potential Match:** Meets most critical skills and some preferred skills. May need additional training for some skills.
        * **Not a Match:** Lacks several critical skills or has limited experience in Data Engineering, ML, and Generative AI. 
     
     **Reasons:** Provide three reasons in bullets for the selection decision
     
     **Input:**
     Resume: {resume_json}
     Job Description: {jd_json}
     Additional input: {additional_inputs}
     
     I want the response as a JSON object with the following structure. DO not add any other text to the response apart from the json:
    {{
    "Selection": "Strong Match",
    "Score": 90.0,
    "Name": "Matthew Bordin",
    "Contact-Email": "mattbn34@xyz.com", 
    "Contact-Phone": "+44-454536456",
    "resume": "{files.name}",
    "Primary-Skills": "Python, DBT, Airflow",
    "Secondary-Skills": "AWS, Azure, DevOps",
    "Reasons": ["","",""]
    }}
    """

    response_text = get_openai_response(third_prompt)
    results.append(response_text.strip())

    print(type(results))
    return results

st.session_state.submit_button=False

def main():
    st.title("Resume Analyzer with JD Matching")

    with st.sidebar:
        with st.form('Resume Parsing Configuration'):
            st.header("Provide Resume, JD & Details")
            uploaded_files = st.file_uploader("Upload Profiles", accept_multiple_files=True, type=[ 'docx', 'pdf'])
            #folder_path = st.text_input("Path to Resume Folder")
            jd = st.text_area("Job Description (JD)", height=200)
            additional_inputs = st.text_area("Additional Inputs (Optional)", height=100)
            extract_PII = st.toggle('Show Contact Information')
            submit_button = st.form_submit_button('Submit')
    t0 = time.time()
    if uploaded_files and jd and submit_button:
        print('config set - running job')
        results = process_resume(uploaded_files, jd, additional_inputs)
        print(results)
        counter=0
        if results:
            print('Processing extracted Information')
            parsed_results = []
            for result in results:
                print('cleaning unwanted elements in the response')
                cleaned_result = result.strip("```json").strip("```").strip()
                try:
                    all_keys_present_flag=False
                    parsed_result = json.loads(cleaned_result)
                    if extract_PII:
                        if all(key in parsed_result for key in ["Name", "Contact-Email", "Contact-Phone", "resume", "Score", "Selection", "Primary-Skills", "Secondary-Skills", "Reasons"]):
                            all_keys_present_flag=True
                            print('Information (PII) extracted for {0}  = {1}'.format(parsed_result['Name'], all_keys_present_flag))
                    else:
                        if all(key in parsed_result for key in ["Name", "resume", "Score", "Selection", "Primary-Skills", "Secondary-Skills", "Reasons"]):
                            all_keys_present_flag=True
                            print('Information extracted for {0}  = {1}'.format(parsed_result['Name'], all_keys_present_flag))

                    if all_keys_present_flag:
                        print('Total elements present in Resume-analyzed-bucket: {0}'.format(len(parsed_results)))
                        print('Information Extraction Verified')
                        parsed_result["Reasons"] = ", ".join(parsed_result["Reasons"])
                        parsed_results.append(parsed_result)
                        counter=counter+1
                        print('Processed {0} Resume'.format(counter))
                    else:
                        st.warning(f"Skipping output as it doesn't match expected format: {result}")
                except json.JSONDecodeError:
                    st.warning(f"Skipping invalid JSON: {result}")

            if parsed_results:
                # Create a DataFrame from the parsed results
                #df = pd.DataFrame(parsed_results)
                df = pd.json_normalize(parsed_results)
                if not extract_PII:
                    print('Removing contact information from results')
                    df.drop(columns=["Contact-Email", "Contact-Phone"], inplace=True)
                print('Generating output for the following fields: {0}'.format(list(df.columns)))
                df["Score"] = pd.to_numeric(df["Score"])
                df_styled=df.style.map(color_selection, subset=['Selection'])
                st.dataframe(df_styled,
                            column_config={
                                "Score": st.column_config.ProgressColumn(
                                    "Score",
                                    help="The Score in percentage",
                                    format="%d",
                                    min_value=0,
                                    max_value=100,
                                ),
                                "Primary-Skills":st.column_config.TextColumn("Primary-Skills", width="small"),
                                "Secondary-Skills":st.column_config.TextColumn("Secondary-Skills", width="small"),
                                "Reasons":st.column_config.TextColumn("Reasons", width="small"),
                            },
                            hide_index=True,
                        )
            else:
                st.write("No valid resumes found.")
        else:
            st.write("No resumes found in the specified folder.")
    else:
        print('Mandatory Config Not provided yet')
    t1 = time.time()
    print(t1-t0)
    with st.sidebar:
        st.image("./img/logo.png")
        