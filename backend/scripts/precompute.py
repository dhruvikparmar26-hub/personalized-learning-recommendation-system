"""
Pre-compute TF-IDF vectors and similarity matrix.

Run this script once after loading courses into the database or CSV.
Output is saved to data/processed/ and loaded during app startup.

Usage:
    cd backend
    python -m scripts.precompute
"""

import os
import sys
import pandas as pd
import logging

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.recommender import recommender

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
DATA_PROCESSED = os.path.join(os.path.dirname(__file__), "..", "data", "processed")


def load_coursera_csv() -> pd.DataFrame:
    """Load and clean the Coursera dataset CSV."""
    csv_path = os.path.join(DATA_RAW, "Coursera.csv")

    if not os.path.exists(csv_path):
        logger.info("Coursera.csv not found. Generating sample data...")
        return generate_sample_courses()

    logger.info(f"Loading {csv_path}")
    df = pd.read_csv(csv_path)

    # Standardize column names
    col_map = {
        "Course Name": "name",
        "University": "university",
        "Difficulty Level": "difficulty",
        "Course Rating": "rating",
        "Course URL": "url",
        "Course Description": "description",
        "Skills": "skills",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Add ID if missing
    if "id" not in df.columns:
        import uuid
        df["id"] = [str(uuid.uuid4()) for _ in range(len(df))]

    # Clean
    df["rating"] = pd.to_numeric(df.get("rating", 0), errors="coerce").fillna(0.0)
    df["description"] = df.get("description", "").fillna("")
    df["skills"] = df.get("skills", "").fillna("")
    df["name"] = df.get("name", "").fillna("Untitled")

    logger.info(f"Loaded {len(df)} courses")
    return df


def generate_sample_courses() -> pd.DataFrame:
    """Generate sample course data for development/testing."""
    import uuid
    courses = [
        {"name": "Python for Everybody", "university": "University of Michigan", "difficulty": "Beginner", "rating": 4.8, "description": "Learn Python programming from scratch. Variables, loops, functions, data structures. Perfect for beginners with no programming experience.", "skills": "Python, Programming, Data Structures, Web Scraping"},
        {"name": "Machine Learning", "university": "Stanford University", "difficulty": "Intermediate", "rating": 4.9, "description": "Comprehensive machine learning course covering supervised learning, unsupervised learning, neural networks, and best practices.", "skills": "Machine Learning, Python, TensorFlow, Neural Networks, Statistics"},
        {"name": "Data Science Specialization", "university": "Johns Hopkins University", "difficulty": "Intermediate", "rating": 4.5, "description": "Complete data science workflow from data cleaning to visualization to machine learning and reproducible research.", "skills": "R, Data Analysis, Statistics, Machine Learning, Data Visualization"},
        {"name": "Deep Learning Specialization", "university": "DeepLearning.AI", "difficulty": "Advanced", "rating": 4.9, "description": "Master deep learning fundamentals including CNNs, RNNs, LSTM, transformers. Build and train deep neural networks.", "skills": "Deep Learning, Neural Networks, TensorFlow, Python, Computer Vision, NLP"},
        {"name": "Web Development with React", "university": "Meta", "difficulty": "Intermediate", "rating": 4.7, "description": "Build modern web applications with React. Components, state management, hooks, routing, and API integration.", "skills": "React, JavaScript, HTML, CSS, Web Development, Frontend"},
        {"name": "SQL for Data Science", "university": "UC Davis", "difficulty": "Beginner", "rating": 4.6, "description": "Learn SQL fundamentals for data science. Querying databases, joins, aggregations, and subqueries.", "skills": "SQL, Database, Data Analysis, Data Management"},
        {"name": "Google IT Automation with Python", "university": "Google", "difficulty": "Beginner", "rating": 4.7, "description": "Automate IT tasks with Python. Version control with Git, troubleshooting, cloud computing basics.", "skills": "Python, Automation, Git, Cloud Computing, Linux"},
        {"name": "AWS Cloud Solutions Architect", "university": "Amazon Web Services", "difficulty": "Intermediate", "rating": 4.6, "description": "Design and deploy scalable systems on AWS. EC2, S3, Lambda, VPC, and cloud architecture patterns.", "skills": "AWS, Cloud Computing, DevOps, Architecture, Networking"},
        {"name": "Natural Language Processing", "university": "DeepLearning.AI", "difficulty": "Advanced", "rating": 4.8, "description": "NLP with attention models, transformers, and sequence-to-sequence architectures. Text classification, sentiment analysis.", "skills": "NLP, Python, Deep Learning, Transformers, Text Processing"},
        {"name": "Statistics with Python", "university": "University of Michigan", "difficulty": "Intermediate", "rating": 4.5, "description": "Statistical analysis using Python. Hypothesis testing, regression, probability distributions, and Bayesian methods.", "skills": "Statistics, Python, Data Analysis, Probability, Regression"},
        {"name": "Full-Stack Web Development", "university": "The Hong Kong University", "difficulty": "Intermediate", "rating": 4.5, "description": "Complete full-stack development with Node.js, Express, MongoDB, and React. Build real-world applications.", "skills": "JavaScript, Node.js, React, MongoDB, Express, Full-Stack"},
        {"name": "Introduction to Computer Science", "university": "Harvard University", "difficulty": "Beginner", "rating": 4.9, "description": "CS50 - Harvard's introduction to computer science. Algorithms, data structures, C, Python, SQL, web development.", "skills": "Computer Science, Algorithms, C, Python, SQL, Data Structures"},
        {"name": "Google Data Analytics Certificate", "university": "Google", "difficulty": "Beginner", "rating": 4.8, "description": "Professional data analytics certificate. Spreadsheets, SQL, R, Tableau, data cleaning and visualization.", "skills": "Data Analytics, SQL, R, Tableau, Data Visualization, Spreadsheets"},
        {"name": "Agile Project Management", "university": "Google", "difficulty": "Beginner", "rating": 4.7, "description": "Agile project management methodologies. Scrum framework, sprints, retrospectives, and stakeholder management.", "skills": "Project Management, Agile, Scrum, Leadership, Communication"},
        {"name": "TensorFlow Developer Certificate", "university": "DeepLearning.AI", "difficulty": "Intermediate", "rating": 4.7, "description": "Prepare for TensorFlow certification. Build neural networks, image classification, NLP, and time series models.", "skills": "TensorFlow, Deep Learning, Python, Computer Vision, NLP"},
        {"name": "Docker and Kubernetes", "university": "IBM", "difficulty": "Intermediate", "rating": 4.5, "description": "Container orchestration with Docker and Kubernetes. Microservices architecture, deployment, scaling.", "skills": "Docker, Kubernetes, DevOps, Microservices, Cloud Computing"},
        {"name": "Business Strategy Specialization", "university": "University of Virginia", "difficulty": "Intermediate", "rating": 4.5, "description": "Strategic analysis, competitive advantage, and business model innovation. Case studies from real companies.", "skills": "Business Strategy, Management, Leadership, Analysis, Innovation"},
        {"name": "Cybersecurity Specialization", "university": "University of Maryland", "difficulty": "Intermediate", "rating": 4.5, "description": "Cybersecurity fundamentals. Network security, cryptography, risk management, and ethical hacking.", "skills": "Cybersecurity, Network Security, Cryptography, Risk Management"},
        {"name": "Data Visualization with Tableau", "university": "UC Davis", "difficulty": "Beginner", "rating": 4.5, "description": "Create compelling data visualizations with Tableau. Dashboards, storytelling with data, best practices.", "skills": "Tableau, Data Visualization, Data Analysis, Dashboard Design"},
        {"name": "Advanced Machine Learning on GCP", "university": "Google Cloud", "difficulty": "Advanced", "rating": 4.4, "description": "End-to-end ML on Google Cloud Platform. Feature engineering, model training, MLOps, AutoML.", "skills": "Machine Learning, Google Cloud, MLOps, TensorFlow, Big Data"},
        {"name": "iOS App Development with Swift", "university": "University of Toronto", "difficulty": "Intermediate", "rating": 4.8, "description": "Build native iOS apps using Swift and SwiftUI. Navigation, data persistence, and App Store deployment.", "skills": "Swift, iOS, Mobile, App Development, UI"},
        {"name": "Android App Development with Kotlin", "university": "Google", "difficulty": "Beginner", "rating": 4.7, "description": "Create Android applications using Kotlin. Activities, fragments, Room database, and Material Design.", "skills": "Android, Kotlin, Mobile, App Development, Java"},
        {"name": "Google UX Design Professional Certificate", "university": "Google", "difficulty": "Beginner", "rating": 4.9, "description": "Foundations of UX design, creating wireframes, prototypes, and conducting user research with Figma.", "skills": "Figma, Design, UI, UX, User Experience, Prototyping"},
        {"name": "UI / UX Design Specialization", "university": "CalArts", "difficulty": "Intermediate", "rating": 4.6, "description": "Visual elements of user interface design, user experience fundamentals, and web design strategy.", "skills": "Design, UI, UX, Wireframing, Web Design"},
        {"name": "Introduction to Game Development with Unity", "university": "Michigan State University", "difficulty": "Beginner", "rating": 4.7, "description": "Learn 2D and 3D game development using Unity engine and C#. Physics, animation, and game logic.", "skills": "Unity, C#, Game Development, Programming, 3D"},
        {"name": "Unreal Engine C++ Developer", "university": "Epic Games", "difficulty": "Intermediate", "rating": 4.8, "description": "Master Unreal Engine by building real games. C++ programming, blueprints, and multiplayer networking.", "skills": "Unreal Engine, C++, Game Development, Multiplayer"},
        {"name": "Blockchain Basics and Smart Contracts", "university": "University at Buffalo", "difficulty": "Intermediate", "rating": 4.5, "description": "Understanding blockchain technology, Ethereum, and writing smart contracts with Solidity.", "skills": "Blockchain, Crypto, Solidity, Smart Contracts, Web3"},
        {"name": "Finance for Non-Financial Professionals", "university": "UC Irvine", "difficulty": "Beginner", "rating": 4.6, "description": "Impact of financial decisions on profitability. Financial statements, budgeting, and investment analysis.", "skills": "Finance, Accounting, Business, Management, Budgeting"},
        {"name": "FinTech and Cryptocurrency", "university": "Wharton School", "difficulty": "Advanced", "rating": 4.7, "description": "The future of financial technology. Robo-advising, crowdfunding, mobile payments, and crypto assets.", "skills": "Fintech, Crypto, Finance, Blockchain, Business"},
    ]

    for c in courses:
        c["id"] = str(uuid.uuid4())
        c["num_reviews"] = 0
        c["url"] = f"https://coursera.org/learn/{c['name'].lower().replace(' ', '-')}"

    return pd.DataFrame(courses)


def main():
    """Main precomputation pipeline."""
    os.makedirs(DATA_RAW, exist_ok=True)
    os.makedirs(DATA_PROCESSED, exist_ok=True)

    # Load data
    df = load_coursera_csv()
    logger.info(f"Courses loaded: {len(df)}")

    # Fit recommender
    recommender.fit(df)

    # Save model
    recommender.save(DATA_PROCESSED)
    logger.info(f"Model saved to {DATA_PROCESSED}")

    # Test: get recommendations for sample tags
    test_tags = ["python", "machine learning"]
    recs = recommender.recommend_for_user(test_tags, top_n=5)
    logger.info(f"\nTest recommendations for {test_tags}:")
    for r in recs:
        logger.info(f"  {r['course_name']} (score: {r['similarity_score']:.3f})")


if __name__ == "__main__":
    main()
