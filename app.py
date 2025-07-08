import streamlit as st
import pdfplumber
import docx
import requests
import pandas as pd
import plotly.express as px
import json

from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import plotly.graph_objects as go


def generate_updated_resume(resume_text, ats_tips):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    section_style = styles['Heading2']
    normal_style = ParagraphStyle(
        'NormalStyle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        leading=14
    )

    # Convert resume into sections
    content = []
    lines = resume_text.split('\n')
    section_title = None
    section_buffer = []
    resume_sections = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.isupper() or line.endswith(":"):  # crude section detection
            if section_title:
                resume_sections[section_title] = section_buffer
            section_title = line.strip(":").upper()
            section_buffer = []
        else:
            section_buffer.append(line)

    if section_title:
        resume_sections[section_title] = section_buffer

    # Apply ATS tips
    if ats_tips:
        if isinstance(ats_tips[0], dict):
            for tip in ats_tips:
                section = tip.get("section", "").upper()
                keywords = tip.get("keywords_to_add", [])
                suggestion = tip.get("suggested_change", "")

                if section in resume_sections:
                    if keywords:
                        resume_sections[section].append("Keywords: " + ", ".join(keywords))
                    if suggestion:
                        resume_sections[section].append("Note: " + suggestion)
        elif isinstance(ats_tips[0], str):
            resume_sections["ATS OPTIMIZATION NOTES"] = [f"- {tip}" for tip in ats_tips]

    # Write updated resume content
    content.append(Paragraph("Updated Resume with ATS Optimizations", styles['Title']))
    content.append(Spacer(1, 12))

    for section, items in resume_sections.items():
        content.append(Paragraph(section, section_style))
        for item in items:
            content.append(Paragraph(item, normal_style))
        content.append(Spacer(1, 12))

    doc.build(content)
    buffer.seek(0)
    return buffer


def extract_resume_text(file):
    if file.name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            return "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
    elif file.name.endswith(".docx"):
        doc = docx.Document(file)
        return "\n".join([para.text for para in doc.paragraphs])
    return ""


def call_chat_groq(prompt, api_key):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a professional resume evaluator and career advisor."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def get_match_analysis_prompt(resume_text, job_description):
    return f"""
    You are a resume and job description matcher.

    Compare the following resume and job description and return:
    1. A match score (0-100)
    2. Work experience relevance (brief explanation)
    3. Education relevance (brief explanation)
    4. Recommendations to improve match (list of 3–5)
    5. ATS optimization suggestions (2–3 tips)

    Resume:
    {resume_text}

    Job Description:
    {job_description}

    Format your response as only valid JSON like this:
    {{
      "match_score": 85,
      "experience_match": "...",
      "education_match": "...",
      "recommendations": ["..."],
      "ats_tips": ["..."]
    }}
    DO NOT add extra comments or markdown.
    """


def get_skill_match_prompt(resume_text, job_description):
    return f"""
    Compare the resume and job description.

    --- Resume ---
    {resume_text}

    --- Job Description ---
    {job_description}

    Output only JSON:
    {{
    "matching_skills": ["Python"],
    "missing_skills": [
        {{"skill": "Docker", "suggestion": "Add Docker"}},
        {{"skill": "Kubernetes", "suggestion": "Mention Kubernetes"}}
    ]
    }}
    DO NOT add explanations or markdown.
    """


def get_full_analysis_prompt(match_analysis):
    return f"""
    Evaluate ATS score from the below analysis:

    --- Analysis ---
    {json.dumps(match_analysis, indent=2)}

    Return JSON:
    {{
    "ats_score": 78,
    "explanation": "...",
    "strengths": ["..."],
    "weaknesses": ["..."]
    }}
    DO NOT add markdown or comments.
    """


def get_cover_letter_prompt(resume_text, job_description, match_analysis, tone="professional"):
    return f"""
    Write a cover letter for the job described below using a {tone} tone.

    --- Job Description ---
    {job_description}

    --- Resume ---
    {resume_text}

    --- Match Analysis ---
    {json.dumps(match_analysis, indent=2)}

    Return plain text only, no formatting or markdown.
    """


# === Streamlit App Starts ===
st.sidebar.title("Enter Groq Key")
groq_api_key = st.sidebar.text_input("Enter your Groq API key", type="password")

st.title("ImprovityResume Enhancer")
job_description = st.text_area("Paste the job description", height=200)
upload_file = st.file_uploader("Upload your resume (PDF or DOCX)", type=["pdf", "docx"])

if st.button("Submit"):
    if not upload_file or not job_description or not groq_api_key:
        st.warning("Please provide all inputs")
    else:
        resume_text = extract_resume_text(upload_file)
        st.session_state["groq_api_key"] = groq_api_key
        st.session_state["job_description"] = job_description
        st.session_state["resume text"] = resume_text

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "Skill Analysis 🧠", "Experience Match 🗂️", "Recommendations 💡",
            "Cover Letter 📄", "ATS Summary 📊", "Updated Resume 📄"
        ])

        with tab1:
            try:
                skill_prompt = get_skill_match_prompt(resume_text, job_description)
                skill_json = json.loads(call_chat_groq(skill_prompt, groq_api_key))
                st.session_state["matching_skills"] = skill_json.get("matching_skills", [])
                st.session_state["missing_skills"] = skill_json.get("missing_skills", [])
            except Exception as e:
                st.error(f"Skill matching error: {e}")

            st.subheader("Matching Skills")
            st.success(", ".join(st.session_state.get("matching_skills", [])))

            st.subheader("Missing Skills")
            for item in st.session_state.get("missing_skills", []):
                st.warning(f"{item['skill']}: {item['suggestion']}")

            df = pd.DataFrame({
                "Skill Type": ["Matching", "Missing"],
                "Count": [len(st.session_state["matching_skills"]), len(st.session_state["missing_skills"])]
            })
            st.plotly_chart(px.bar(df, x="Skill Type", y="Count", color="Skill Type", title="Skill Overview"))

        with tab2:
            try:
                match_prompt = get_match_analysis_prompt(resume_text, job_description)
                match_json = json.loads(call_chat_groq(match_prompt, groq_api_key))
                st.session_state["match_analysis"] = match_json

                st.success("Work Experience: " + match_json["experience_match"])
                st.success("Education: " + match_json["education_match"])
            except Exception as e:
                st.error(f"Experience match error: {e}")

        with tab3:
            try:
                recs = st.session_state["match_analysis"].get("recommendations", [])
                tips = st.session_state["match_analysis"].get("ats_tips", [])
                for r in recs:
                    st.info(f"- {r}")
                for t in tips:
                    st.warning(f"- {t}")
            except Exception as e:
                st.error(f"Recommendation error: {e}")

        with tab4:
            try:
                prompt = get_cover_letter_prompt(resume_text, job_description, st.session_state["match_analysis"])
                cover_text = call_chat_groq(prompt, groq_api_key)
                st.text_area("Generated Cover Letter", value=cover_text, height=300)
                st.download_button("📥 Download Cover Letter", cover_text, "cover_letter.txt", "text/plain")
            except Exception as e:
                st.error(f"Cover letter error: {e}")

        with tab5:
            try:
                summary_prompt = get_full_analysis_prompt(st.session_state["match_analysis"])
                ats_summary = json.loads(call_chat_groq(summary_prompt, groq_api_key))
                st.session_state["ats_summary"] = ats_summary

                st.metric("ATS Score", f"{ats_summary['ats_score']}/100")
                st.info("Why this score: " + ats_summary["explanation"])
                st.success("Strengths: " + ", ".join(ats_summary["strengths"]))

                weaknesses = ats_summary.get("weaknesses", [])
                if isinstance(weaknesses, str):
                    weaknesses = [weaknesses]
                st.error("Weaknesses: " + ", ".join(weaknesses))
            except Exception as e:
                st.error(f"ATS summary error: {e}")

        with tab6:
            try:
                ats_tips = st.session_state["match_analysis"].get("ats_tips", [])
                updated_pdf = generate_updated_resume(resume_text, ats_tips)
                st.download_button("📥 Download Updated Resume", updated_pdf, "updated_resume.pdf", "application/pdf")
            except Exception as e:
                st.error(f"Updated resume error: {e}")
