@echo off
cd /d "C:\Users\nande\Desktop\projects\home-assistant-sam"
"C:\Users\nande\Desktop\projects\home-assistant-sam\.venv\Scripts\python.exe" -m windows_agent.main --minimized >> "C:\Users\nande\Desktop\projects\home-assistant-sam\logs\agent_startup.log" 2>&1
