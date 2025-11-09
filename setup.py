from setuptools import setup, find_packages

setup(
    name="qwen-dba",
    version="0.1.0",
    description="AI-powered Database Administrator using Qwen-MLX",
    author="Your Team",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "mlx>=0.10.0",
        "mlx-lm>=0.10.0",
        "numpy>=1.24.0",
        "pydantic>=2.0.0",
        "pyyaml>=6.0",
        "python-dotenv>=1.0.0",
        "psycopg2-binary>=2.9.0",
        "sqlalchemy>=2.0.0",
        "chromadb>=0.4.0",
        "prometheus-client>=0.19.0",
        "click>=8.1.0",
        "rich>=13.0.0",
        "tabulate>=0.9.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.5.0",
        ]
    },
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "qwen-dba=qwen_dba.cli:main",
        ],
    },
)
