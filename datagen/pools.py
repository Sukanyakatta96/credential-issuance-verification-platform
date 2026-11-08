FIRST_NAMES = """Aarav Aditi Aisha Akira Alberto Alejandra Alexei Amara Amir Ana Anaya Andre Anika Anjali Antonio Arjun Aryan Astrid
Ayesha Beatriz Benjamin Bianca Bogdan Camila Carlos Chen Chiara Chloe Daniel Dara Deepak Diego Divya Dmitri Elena Elif Emeka
Emma Esteban Fatima Felix Fiona Gabriel Gauri Giulia Hana Hassan Hiro Ibrahim Ines Ioana Isabel Ishaan Jada Jakub Jamal
Jasmine Javier Jin Joao Jonas Julia Kabir Kai Kamala Karim Katarina Kavya Kenji Kiran Lakshmi Lars Laura Leila Leo Liam
Lina Luca Lucia Mahesh Maira Malik Mansi Marco Maria Mateo Maya Mei Mikhail Mira Mohammed Nadia Naveen Neha Nia Nikhil Nina
Noah Olga Omar Oscar Pablo Pooja Priya Rafael Rahul Rania Ravi Rhea Rohan Rosa Rui Sahil Salma Samir Sana Sara Sergio Shreya
Siddharth Sofia Sunita Tariq Tenzin Thandiwe Tomas Uma Valentina Vikram Wei Yara Yasmin Yuki Zainab Zoe""".split()

LAST_NAMES = """Abdullah Adeyemi Agarwal Ahmed Alvarez Anderson Banerjee Bauer Becker Bianchi Bose Brown Campbell Castillo Chatterjee
Chaudhary Chen Choi Clarke Cohen Costa Das Davies Dias Dubois Dutta Edwards Evans Fernandez Fischer Flores Garcia Gill Gomez
Gupta Hansen Hashimi Hernandez Hughes Hussain Iyer Jackson Jain Jensen Johnson Joshi Kapoor Kaur Khan Kim Klein Kowalski
Kumar Lee Lewis Li Lopez Machado Mahajan Malhotra Martin Martinez Mehta Meyer Miller Mishra Mitchell Moreno Mukherjee Murphy
Nair Nakamura Nguyen Novak Okafor Oliveira Ortiz Osei Pandey Park Patel Pereira Petrov Pillai Popov Prasad Qureshi Rahman
Rao Reddy Reyes Richter Rivera Rodriguez Roy Russo Saha Sanchez Santos Sato Schmidt Schneider Sen Shah Sharma Silva Singh
Smith Sokolov Soto Suarez Sullivan Tanaka Taylor Thomas Tiwari Torres Tran Varga Verma Vasquez Wagner Walker Wang Weber
White Williams Wilson Wong Wright Yadav Yamamoto Young Zhang Zhou Zimmermann""".split()

COUNTRIES = [("IN", 30), ("US", 20), ("GB", 9), ("DE", 6), ("CA", 6), ("AU", 5), ("SG", 4), ("AE", 4), ("BR", 5), ("ZA", 3), ("FR", 4), ("NG", 4)]

DEPARTMENTS = ["Data and Analytics", "Computing", "Business School", "Health Sciences", "Design", "Engineering", "Sustainability", "Finance"]

CATEGORIES = {
    "Data Science": ["Statistics", "Data Wrangling", "Visualisation", "Predictive Modelling", "Experiment Design", "Time Series", "Data Ethics", "SQL Analytics"],
    "Software Engineering": ["Python Programming", "Web Development", "Testing Practices", "Databases", "API Design", "Version Control", "Algorithms", "Code Review"],
    "Cybersecurity": ["Network Defence", "Secure Coding", "Incident Response", "Cryptography Basics", "Threat Modelling", "Identity Management", "Forensics", "Security Governance"],
    "Business Analytics": ["Dashboards", "KPI Design", "Forecasting", "Pricing Analytics", "Customer Segmentation", "Operations Analytics", "Decision Models", "Reporting Standards"],
    "Digital Marketing": ["Search Marketing", "Content Strategy", "Email Campaigns", "Social Analytics", "Brand Positioning", "Conversion Testing", "Marketing Automation", "Audience Research"],
    "Healthcare Informatics": ["Clinical Data", "Health Records", "Medical Coding", "Privacy in Health", "Population Health", "Telehealth Systems", "Quality Metrics", "Interoperability"],
    "Project Management": ["Planning", "Risk Management", "Agile Delivery", "Stakeholder Communication", "Budgeting", "Scheduling", "Quality Assurance", "Portfolio Management"],
    "UX Design": ["User Research", "Interaction Design", "Prototyping", "Accessibility", "Information Architecture", "Usability Testing", "Design Systems", "Service Design"],
    "Cloud Computing": ["Cloud Foundations", "Containers", "Infrastructure as Code", "Cloud Security", "Serverless", "Cost Management", "Monitoring", "Networking"],
    "Finance": ["Financial Statements", "Corporate Valuation", "Risk Analytics", "Budget Control", "Audit Basics", "Treasury", "Investment Analysis", "Regulatory Reporting"],
    "Sustainability": ["Carbon Accounting", "Circular Economy", "Energy Systems", "ESG Reporting", "Sustainable Supply Chains", "Climate Risk", "Resource Planning", "Policy Analysis"],
    "AI and Machine Learning": ["Machine Learning", "Neural Networks", "Natural Language", "Computer Vision", "Model Deployment", "Responsible AI", "Feature Engineering", "Evaluation Methods"],
}
LEVEL_SUFFIX = {"introductory": ["Fundamentals", "Essentials", "Foundations"],
                "intermediate": ["in Practice", "Applied", "Workshop"],
                "advanced": ["Advanced", "Masterclass", "Specialist Track"]}

ISSUER_NAMES = [
    "Northfield University Continuing Education", "Lakeshore Institute of Technology", "Meridian College of Business",
    "Harbor Digital Academy", "Summit Health Sciences Institute", "Cascade Open Learning Alliance",
    "Northfield Global Learning", "Lakeshore Professional Institute",
]

REQUESTER_ORGS = ["Orbit Staffing", "Brightpath Recruiting", "Kestrel Analytics", "Vantage Consulting", "Aster Health Trust",
                  "Pioneer Bank", "Greenfield Council", "Nimbus Cloud Services", "Lighthouse Schools", "Atlas Logistics",
                  "Meridian Talent Partners", "Helix Biotech", "Fjord Software", "Crescent University Admissions"]

REVOCATION_REASONS = [
    ("issued_in_error", 25, "Issued before records were reconciled"),
    ("academic_misconduct", 20, "Assessment integrity review upheld"),
    ("fraud", 15, "Identity or evidence found to be fraudulent"),
    ("learner_request", 25, "Learner asked for withdrawal of the credential"),
    ("rule_change", 15, "Credential requirements were corrected retroactively"),
]
