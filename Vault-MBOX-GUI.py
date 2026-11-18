import mailbox
import os
import glob
import re
import json
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from email import policy
from email.parser import BytesParser

def sanitize_filename(name):
    # Strip tabs, newlines, and control characters (\x00-\x1f and \x7f)
    clean_name = re.sub(r'[\x00-\x1f\x7f]', ' ', str(name))
    # Remove invalid Windows file path characters
    clean_name = re.sub(r'[\\/*?:"<>|]', "", clean_name)
    # Collapse multiple spaces and truncate
    clean_name = " ".join(clean_name.split())
    return clean_name[:100].strip()

def select_folder():
    folder_path = filedialog.askdirectory(title="Select folder containing .mbox files")
    if not folder_path: return
        
    mbox_files = glob.glob(os.path.join(folder_path, "*.mbox"))
    if not mbox_files:
        messagebox.showerror("Error", f"No .mbox files found in:\n{folder_path}")
        return
        
    btn_browse.config(state=tk.DISABLED)
    lbl_status.config(text="Processing... Please wait.")
    progress.start(15)
    
    threading.Thread(target=process_files, args=(folder_path, mbox_files), daemon=True).start()

def process_files(export_path, mbox_files):
    index_path = os.path.join(export_path, "MasterIndex.html")
    output_dir = os.path.join(export_path, "extracted_emails")
    attachments_dir = os.path.join(output_dir, "attachments")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(attachments_dir, exist_ok=True)

    search_data = []
    list_items = []
    email_counter = 0

    for mbox_file in mbox_files:
        mb = mailbox.mbox(mbox_file)
        for message in mb:
            msg = BytesParser(policy=policy.default).parsebytes(bytes(message))
            subject = str(msg.get("Subject", "(No Subject)"))
            sender = str(msg.get("From", "Unknown Sender"))
            date = str(msg.get("Date", "Unknown Date"))
            
            text_body, html_body, attachments_html = "", "", ""
            
            for part in msg.walk():
                if part.is_multipart(): continue
                    
                content_type = part.get_content_type()
                filename = part.get_filename()
                
                if filename:
                    safe_attach_name = sanitize_filename(filename)
                    unique_attach_name = f"{email_counter:04d}_{safe_attach_name}"
                    attach_path = os.path.join(attachments_dir, unique_attach_name)
                    
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            with open(attach_path, "wb") as f:
                                f.write(payload)
                            attachments_html += f"<a href='attachments/{unique_attach_name}' target='_blank'>📎 {safe_attach_name}</a> "
                    except Exception: pass
                else:
                    try:
                        if content_type == "text/plain" and not text_body:
                            text_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
                        elif content_type == "text/html" and not html_body:
                            html_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
                    except Exception: pass
                        
            final_html = html_body if html_body else f"<pre>{text_body}</pre>"
            clean_text = re.sub(r'<[^>]+>', ' ', html_body) if html_body else text_body
            
            safe_subject = sanitize_filename(subject) if subject else "Email"
            file_name = f"{email_counter:04d}_{safe_subject}.html"
            relative_path = f"extracted_emails/{file_name}"
            full_path = os.path.join(output_dir, file_name)
            
            attach_block = f"<div style='margin-top:10px;'><strong>Attachments:</strong><br>{attachments_html}</div>" if attachments_html else ""
            
            header_block = f"""
            <div style="background:#f1f3f4; padding:15px; border-bottom:1px solid #dadce0; font-family:Arial; margin-bottom:20px;">
                <p style="margin:0 0 5px 0;"><strong>From:</strong> {sender}</p>
                <p style="margin:0 0 5px 0;"><strong>Subject:</strong> {subject}</p>
                <p style="margin:0;"><strong>Date:</strong> {date}</p>
                {attach_block}
            </div>
            """
            
            full_email_content = header_block + final_html

            with open(full_path, "w", encoding="utf-8", errors="ignore") as f:
                f.write(f"""<button onclick="window.print()" style="position:fixed; right:15px; top:15px; padding:8px 16px; background-color:#1a73e8; color:white; border:none; border-radius:4px; cursor:pointer;">Print</button>""" + full_email_content)
            
            clean_text = " ".join(clean_text.split())
            
            search_data.append({
                "id": email_counter,
                "name": subject,
                "sender": sender,
                "path": relative_path,
                "content": clean_text,
                "html_payload": full_email_content
            })
            
            list_items.append(
                f"<li class='email-item' onclick=\"loadEmail('{relative_path}', this)\">"
                f"<input type='checkbox' class='print-cb' data-id='{email_counter}' onclick='event.stopPropagation();' style='float:left; margin-right:10px;'>"
                f"<strong>{subject}</strong><br><span style='color:#5f6368; font-size:12px;'>{sender}</span></li>"
            )
            
            email_counter += 1

    # CRITICAL FIX: Convert HTML characters to Unicode to prevent </script> tags in emails from breaking the JSON payload
    js_search_data = json.dumps(search_data).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

    html_header = f"""<!DOCTYPE html>
    <html><head><style>
        body {{ font-family: Arial, sans-serif; display: flex; height: 100vh; margin: 0; }}
        #sidebar {{ width: 35%; overflow-y: auto; padding: 20px; border-right: 1px solid #ccc; }}
        #viewer-container {{ width: 65%; display: flex; flex-direction: column; }}
        iframe {{ flex-grow: 1; border: none; }}
        li {{ padding: 10px; border-bottom: 1px solid #eee; cursor: pointer; list-style: none; }}
        li:hover {{ background: #f8f9fa; }}
        button {{ padding: 8px 16px; background: #1a73e8; color: white; border: none; cursor: pointer; }}
    </style></head><body>
        <div id="sidebar">
            <input type="text" id="searchInput" onkeyup="filterList()" placeholder="Search..." style="width:100%; padding:8px; margin-bottom:15px;">
            <button onclick="compileAndPrint()" style="width:100%; margin-bottom:15px;">Print Selected</button>
            <ul id="fileList" style="padding:0; margin:0;">
    """

    html_footer = f"""
            </ul>
        </div>
        <div id="viewer-container">
            <iframe id="viewer" src="about:blank"></iframe>
        </div>
        <script>
            const searchData = {js_search_data};
            
            function loadEmail(url, liElement) {{
                document.getElementById('viewer').src = url;
            }}
            
            function filterList() {{
                const query = document.getElementById('searchInput').value.toLowerCase();
                const items = document.querySelectorAll('.email-item');
                
                items.forEach((item, index) => {{
                    const data = searchData[index];
                    const isMatch = data.name.toLowerCase().includes(query) || data.content.toLowerCase().includes(query) || data.sender.toLowerCase().includes(query);
                    item.style.display = isMatch ? "" : "none";
                }});
            }}

            function compileAndPrint() {{
                const checkboxes = document.querySelectorAll('.print-cb:checked');
                if (checkboxes.length === 0) return alert("Select emails to print.");

                let compiledHTML = "<!DOCTYPE html><html><head><title>Batch Export</title>";
                compiledHTML += "<style>@media print {{ .page-break {{ page-break-after: always; }} }}</style></head><body>";

                checkboxes.forEach(cb => {{
                    const id = parseInt(cb.dataset.id);
                    const emailData = searchData.find(e => e.id === id);
                    if (emailData) {{
                        compiledHTML += emailData.html_payload;
                        compiledHTML += "<div class='page-break'></div>";
                    }}
                }});

                compiledHTML += "</body></html>";

                const printWindow = window.open('', '_blank');
                printWindow.document.write(compiledHTML);
                printWindow.document.close();
                setTimeout(() => printWindow.print(), 500);
            }}
        </script>
    </body></html>
    """

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_header + "\n".join(list_items) + html_footer)

    root.after(0, lambda: [progress.stop(), webbrowser.open(f"file:///{index_path.replace(os.sep, '/')}", new=2), sys.exit()])

root = tk.Tk()
root.title("Google Vault Extractor")
root.geometry("400x150")
tk.Label(root, text="Select folder containing .mbox files").pack(pady=10)
btn_browse = tk.Button(root, text="Browse", command=select_folder)
btn_browse.pack()
progress = ttk.Progressbar(root, mode='indeterminate')
progress.pack(pady=10, fill=tk.X, padx=20)
lbl_status = tk.Label(root, text="")
lbl_status.pack()
root.mainloop()