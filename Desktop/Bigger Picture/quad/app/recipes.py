import shlex
import json

class RecipeError(Exception):
    pass

def to_exec_form(command_string: str) -> str:
    """
    "uvicorn main:app --host 0.0.0.0 --port 8000"
    → '["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]'
    Returns a JSON array string suitable for direct insertion into a Dockerfile CMD line.
    """
    parts = shlex.split(command_string)
    return json.dumps(parts)

def generate_dockerfile(detection: dict) -> str:
    """
    Takes the dict returned by detect_stack() from step 1.2.
    Returns a complete, valid Dockerfile as a string.
    Raises RecipeError if stack is unknown or unsupported.
    """
    stack = detection.get("stack")
    if not stack:
        raise RecipeError("Unknown or unsupported stack.")

    stack = stack.lower()
    port = detection.get("port")
    if port is None:
        raise RecipeError("Port must be specified in detection output.")

    if stack == "static":
        return (
            "FROM nginx:alpine\n"
            "COPY . /usr/share/nginx/html\n"
            f"EXPOSE {port}\n"
            'CMD ["nginx", "-g", "daemon off;"]\n'
        )

    elif stack == "node":
        package_manager = detection.get("package_manager", "npm")
        build_command = detection.get("build_command")
        entrypoint = detection.get("entrypoint", "node index.js")
        exec_entrypoint = to_exec_form(entrypoint)

        if build_command is not None:
            return (
                "FROM node:20-alpine AS builder\n"
                "WORKDIR /app\n"
                "COPY package*.json ./\n"
                f"RUN {package_manager} install\n"
                "COPY . .\n"
                f"RUN {build_command}\n\n"
                "FROM node:20-alpine\n"
                "WORKDIR /app\n"
                "COPY --from=builder /app/dist ./dist\n"
                "COPY package*.json ./\n"
                f"RUN {package_manager} install --production\n"
                f"EXPOSE {port}\n"
                f"CMD {exec_entrypoint}\n"
            )
        else:
            return (
                "FROM node:20-alpine\n"
                "WORKDIR /app\n"
                "COPY package*.json ./\n"
                f"RUN {package_manager} install --production\n"
                "COPY . .\n"
                f"EXPOSE {port}\n"
                f"CMD {exec_entrypoint}\n"
            )

    elif stack == "python":
        entrypoint = detection.get("entrypoint")
        notes = detection.get("notes", "")
        use_pyproject = "pyproject.toml" in notes.lower()

        if entrypoint is None:
            exec_entrypoint = '["python", "main.py"]'
            warning_comment = "# WARNING: entrypoint not detected — defaulting to python main.py\n"
        else:
            exec_entrypoint = to_exec_form(entrypoint)
            warning_comment = ""

        if use_pyproject:
            return (
                "FROM python:3.11-slim\n"
                "WORKDIR /app\n"
                "COPY . .\n"
                "RUN pip install --no-cache-dir .\n"
                f"EXPOSE {port}\n"
                f"{warning_comment}CMD {exec_entrypoint}\n"
            )
        else:
            return (
                "FROM python:3.11-slim\n"
                "WORKDIR /app\n"
                "COPY requirements.txt .\n"
                "RUN pip install --no-cache-dir -r requirements.txt\n"
                "COPY . .\n"
                f"EXPOSE {port}\n"
                f"{warning_comment}CMD {exec_entrypoint}\n"
            )

    elif stack == "java":
        package_manager = detection.get("package_manager", "maven")
        if package_manager == "maven":
            return (
                "FROM maven:3.9-eclipse-temurin-21 AS builder\n"
                "WORKDIR /app\n"
                "COPY pom.xml .\n"
                "RUN mvn dependency:go-offline -B\n"
                "COPY src ./src\n"
                "RUN mvn package -DskipTests -B\n\n"
                "FROM eclipse-temurin:21-jre-alpine\n"
                "WORKDIR /app\n"
                "COPY --from=builder /app/target/*.jar app.jar\n"
                f"EXPOSE {port}\n"
                'CMD ["java", "-jar", "app.jar"]\n'
            )
        elif package_manager == "gradle":
            return (
                "FROM gradle:8-jdk21 AS builder\n"
                "WORKDIR /app\n"
                "COPY build.gradle* settings.gradle* ./\n"
                "COPY gradle ./gradle\n"
                "RUN gradle dependencies --no-daemon\n"
                "COPY src ./src\n"
                "RUN gradle bootJar --no-daemon\n\n"
                "FROM eclipse-temurin:21-jre-alpine\n"
                "WORKDIR /app\n"
                "COPY --from=builder /app/build/libs/*.jar app.jar\n"
                f"EXPOSE {port}\n"
                'CMD ["java", "-jar", "app.jar"]\n'
            )
        else:
            raise RecipeError(f"Unsupported package manager for Java: {package_manager}")

    else:
        raise RecipeError(f"Unknown or unsupported stack: {stack}")

def generate_dockerignore(detection: dict) -> str:
    """
    Returns a .dockerignore string appropriate for the detected stack.
    """
    stack = detection.get("stack")
    if not stack:
        raise RecipeError("Unknown or unsupported stack.")

    stack = stack.lower()
    if stack == "static":
        return (
            ".git\n"
            "*.md\n"
            "node_modules\n"
        )
    elif stack == "node":
        return (
            ".git\n"
            "node_modules\n"
            "*.md\n"
            "dist\n"
            ".env\n"
        )
    elif stack == "python":
        return (
            ".git\n"
            "__pycache__\n"
            "*.pyc\n"
            "*.pyo\n"
            ".env\n"
            "venv\n"
            ".venv\n"
        )
    elif stack == "java":
        return (
            ".git\n"
            "target\n"
            "build\n"
            "*.md\n"
            ".env\n"
            "*.class\n"
        )
    else:
        raise RecipeError(f"Unknown or unsupported stack: {stack}")
