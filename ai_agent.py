import os
import logging
import google.generativeai as genai
from PyPDF2 import PdfReader
import magic
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import firestore
from docx import Document
import openpyxl
import time
from google.api_core.exceptions import GoogleAPIError
from difflib import SequenceMatcher
import re

logger = logging.getLogger(__name__)

class AIAgent:
    def __init__(self):
        load_dotenv()
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.model = genai.GenerativeModel('gemini-1.5-flash') #Gemini 1.5 flash is reported to have over 1.8 billion parameters
        self.db = firestore.client()

    def extract_text(self, file_path):
        mime = magic.Magic(mime=True)
        file_type = mime.from_file(file_path)
        text = ""
        try:
            if file_type == 'application/pdf':
                with open(file_path, 'rb') as f:
                    pdf = PdfReader(f)
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
            elif file_type.startswith('text') or file_type in ['application/csv', 'text/csv']:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            elif file_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']:
                doc = Document(file_path)
                for para in doc.paragraphs:
                    text += para.text + "\n"
            elif file_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel']:
                wb = openpyxl.load_workbook(file_path)
                for sheet in wb:
                    for row in sheet.rows:
                        for cell in row:
                            if cell.value:
                                text += str(cell.value) + " "
                        text += "\n"
        except Exception as e:
            logger.error(f"Text extraction failed for {file_path}: {str(e)}")
        return text.strip()

    def store_content(self, file_id, filename, content):
        try:
            if not content:
                logger.warning(f"No content to store for file ID {file_id}: {filename}")
                return
            doc_ref = self.db.collection('file_contents').document(file_id)
            doc_ref.set({
                'file_id': file_id,
                'filename': filename,
                'content': content,
                'timestamp': firestore.SERVER_TIMESTAMP
            })
            logger.info(f"Stored content for file ID {file_id}: {filename}")
        except Exception as e:
            logger.error(f"Failed to store content for {filename}: {str(e)}")

    def delete_content(self, file_id):
        try:
            doc_ref = self.db.collection('file_contents').document(file_id)
            doc_ref.delete()
            logger.info(f"Deleted content for file ID {file_id}")
        except Exception as e:
            logger.error(f"Failed to delete content for file ID {file_id}: {str(e)}")

    def search_content(self, query, user_email, files, n_results=10):
        try:
            file_ids = [f['id'] for f in files]
            logger.debug(f"Searching content for user {user_email}, file IDs: {file_ids}, query: {query}")
            if not file_ids:
                logger.info(f"No file IDs provided for search by {user_email}")
                return []
            docs = self.db.collection('file_contents').where('file_id', 'in', file_ids).stream()
            results = []
            query_words = re.split(r'\s+', query.lower().strip())
            # Simple synonym expansion
            synonyms = {
                'objective': ['goal', 'aim', 'target'],
                'milestone': ['checkpoint', 'stage', 'phase'],
                'project': ['plan', 'initiative', 'task'],
                'deadline': ['timeline', 'due date', 'schedule']
            }
            expanded_query = query_words.copy()
            for word in query_words:
                for key, values in synonyms.items():
                    if word == key:
                        expanded_query.extend(values)
                    elif word in values:
                        expanded_query.append(key)
            expanded_query = list(set(expanded_query))
            logger.debug(f"Expanded query words: {expanded_query}")
            for doc in docs:
                data = doc.to_dict()
                content = data.get('content', '')
                if not content:
                    logger.warning(f"Empty content for file ID {data.get('file_id')}: {data.get('filename')}")
                    continue
                # Clean content
                content_clean = re.sub(r'\s+', ' ', content.strip())
                content_lower = content_clean.lower()
                # Fuzzy matching
                similarity = SequenceMatcher(None, query.lower(), content_lower[:2000]).ratio()
                # Word-based scoring
                word_score = sum(content_lower.count(word) for word in expanded_query)
                # Combined relevance
                relevance = word_score + (similarity * 15)  # Higher weight for similarity
                if relevance > 0.2 or any(word in content_lower for word in expanded_query):
                    results.append({
                        'filename': data['filename'],
                        'content': content_clean[:3000],  # Increased to 3000 chars
                        'relevance': relevance
                    })
                    logger.debug(f"Match for {data['filename']}: relevance={relevance}, similarity={similarity}, word_score={word_score}")
            results.sort(key=lambda x: x['relevance'], reverse=True)
            if not results:
                logger.info(f"No content matches found for query '{query}' by {user_email}, including all files")
                docs = self.db.collection('file_contents').where('file_id', 'in', file_ids).stream()
                for doc in docs:
                    data = doc.to_dict()
                    content = data.get('content', '')
                    if content:
                        content_clean = re.sub(r'\s+', ' ', content.strip())
                        results.append({
                            'filename': data['filename'],
                            'content': content_clean[:3000],
                            'relevance': 0.1
                        })
            logger.debug(f"Returning {len(results)} content matches for query '{query}' by {user_email}")
            return results[:n_results]
        except Exception as e:
            logger.error(f"Content search failed for {user_email}: {str(e)}")
            return []

    def answer_query(self, query, user_email, files):
        try:
            relevant_docs = self.search_content(query, user_email, files)
            context = ""
            if relevant_docs:
                context = "\n".join(
                    f"File: {doc['filename']}\nContent: {doc['content']}\n"
                    for doc in relevant_docs
                )
            # Rephrase query for better alignment
            rephrased_query = query
            if any(keyword in query.lower() for keyword in ['file', 'document', 'upload', 'content']):
                rephrased_query = f"Summarize or extract relevant information from the provided file content to answer: {query}"
            prompt = (
                "You are MegaCloud AI, a highly accurate assistant for a cloud storage platform. "
                "Follow these steps to answer the user's question:\n"
                "1. **Analyze the Question**: Determine if the question refers to uploaded files (e.g., mentions 'file,' 'document,' or specific content). "
                "2. **Use File Content**: If file-related, answer **exclusively** using the provided file content. Quote relevant sections and synthesize information across files if needed. "
                "3. **Handle Complex Queries**: For tasks like summarization, comparison, or inference, break down the question and address each part clearly. "
                "4. **General Questions**: If unrelated to files, provide a precise, accurate, and professional answer using your knowledge. "
                "5. **Format Clearly**: Use markdown (bullet points, quotes, headers) for readability.\n\n"
                f"**User Question**: {rephrased_query}\n\n"
                f"**File Content** (use for file-related questions):\n{context}\n\n"
                "**Answer**:"
            )
            logger.debug(f"Prompt for {user_email}: {prompt[:500]}...")
            for attempt in range(3):
                try:
                    response = self.model.generate_content(
                        prompt,
                        generation_config={
                            'max_output_tokens': 4096,  # Increased for detailed answers
                            'temperature': 0.4,  # High precision
                            'top_p': 0.9,  # Balanced creativity
                            'top_k': 40  # Diverse but focused
                        }
                    )
                    answer = response.text.strip()
                    logger.info(f"AI response for {user_email}: {answer[:100]}...")
                    return answer
                except GoogleAPIError as e:
                    if '429' in str(e) or 'Quota' in str(e).lower():
                        if attempt == 2:
                            logger.error(f"Gemini API quota exceeded for {user_email}: {str(e)}")
                            raise Exception("AI query failed: You have exceeded your Gemini API quota. Please check your Google Cloud billing details.")
                        time.sleep(2 ** attempt)
                        continue
                    logger.error(f"Gemini API error for {user_email}: {str(e)}")
                    raise Exception(f"AI query failed: {str(e)}")
        except Exception as e:
            logger.error(f"AI query failed for {user_email}: {str(e)}")
            raise