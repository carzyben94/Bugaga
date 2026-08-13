import subprocess
result = subprocess.run(["banana-browser", "demo"], capture_output=True)
print(result.stdout.decode())  # Покажет, прошел ли все проверки