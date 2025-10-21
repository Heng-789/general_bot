from setuptools import setup, find_packages

setup(
    name="telegram-scheduler-bot",
    version="1.0.0",
    description="Telegram Bot for scheduling posts",
    author="Your Name",
    python_requires=">=3.8,<3.14",
    install_requires=[
        "python-telegram-bot==20.6",
        "APScheduler==3.10.4",
        "pytz==2023.3",
        "python-dotenv==1.0.0",
    ],
    packages=find_packages(),
)
