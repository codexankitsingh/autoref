# AutoRef – AI-Powered Job Outreach Automation

AutoRef is a locally-hosted tool designed to eliminate manual effort in job application outreach by automating AI-tailored referral emails, sending them directly via your Gmail, tracking replies, and auto-scheduling follow-ups.

## 🚀 How to Run the Application

You'll need two separate terminal windows to run the frontend and backend simultaneously.

### 1. Start the Backend Server (FastAPI)
Open a terminal and navigate to the backend folder:
```bash
cd backend
```
Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
Run the backend API:
```bash
uvicorn main:app --reload --port 8000
# Leave this terminal running!
```

### 2. Start the Frontend App (Next.js)
Open a **second** terminal and navigate to the frontend folder:
```bash
cd frontend
```
Install the Node dependencies:
```bash
npm install
```
Start the development server:
```bash
npm run dev
# Leave this terminal running!
```

## 🎯 How to Use AutoRef

Once both servers are running, access the dashboard by opening your browser to: **[http://localhost:3000](http://localhost:3000)**

### Step 1: Connect your Gmail (Settings)
1. Click on **⚙️ Settings** in the sidebar.
2. Enter the Gmail address you want to send emails from in the **API Status / Gmail API** section and click `+ Add`.
3. AutoRef will open a secure Google Login window. Give AutoRef permission to send emails on your behalf.
4. Paste your resume text / profile background in the "Your Professional Profile" box and save it. Gemini will use this context when writing your referral emails.

### Step 2: Create a New Outreach (New Outreach)
1. Navigate to **✏️ New Outreach** in the sidebar.
2. Paste the **Job Description** (or link) of the job you want to apply for.
3. Click "Parse Job Description". AI will instantly extract the Company, Role, and needed Skills.
4. Enter the recruiter's Name and Email.
5. Click **"Generate Email"**. The AI will draft a highly personalized 150-word email asking for a referral, combining your resume with the job requirements.
6. Review the generated subject and body. Feel free to tweak it manually.
7. Click **"Send Request"**. The email will be sent instantly directly from your connected Gmail.

### Step 3: Track & Forget! (Dashboard)
1. Navigate to **📊 Dashboard** to view all your shipped emails.
2. AutoRef runs a background scheduler. If the recruiter doesn't reply within 3 days, it will automatically generate and send a polite follow-up. 
3. If the recruiter replies, AutoRef's inbox monitor will automatically detect the reply, update the dashboard status to `Replied`, and **cancel** any pending follow-ups so you never double-email them.
4. You can also manually update the status (e.g. from Replied to Interview Scheduled) or sync all your job hunting analytics to a private Google Sheet using the "Sync to Sheets" button!
