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
    # 1. Replace tabs, newlines, and other control characters (\x00-\x1f and \x7f) with a space
    clean_name = re.sub(r'[\x00-\x1f\x7f]', ' ', str(name))
    
    # 2. Remove invalid Windows file path characters
    clean_name = re.sub(r'[\\/*?:"<>|]', "", clean_name)
    
    # 3. Collapse multiple spaces into a single space, strip edges, and truncate to 100 characters
    clean_name = " ".join(clean_name.split())
    
    return clean_name[:100].strip()

def select_folder():
    folder_path = filedialog.askdirectory(title="Select folder containing .mbox files")
    
    if not folder_path:
        return
        
    mbox_files = glob.glob(os.path.join(folder_path, "*.mbox"))
    if not mbox_files:
        messagebox.showerror("Error", f"No .mbox files found in:\n{folder_path}")
        return
        
    btn_browse.config(state=tk.DISABLED)
    lbl_status.config(text="Extracting and indexing emails... Please wait.")
    progress.start(15)
    
    threading.Thread(target=process_files, args=(folder_path, mbox_files), daemon=True).start()

def process_files(export_path, mbox_files):
    index_path = os.path.join(export_path, "MasterIndex.html")
    output_dir = os.path.join(export_path, "extracted_emails")
    attachments_dir = os.path.join(output_dir, "attachments")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    if not os.path.exists(attachments_dir):
        os.makedirs(attachments_dir)

    search_data = []
    list_items = []
    email_counter = 0

    for mbox_file in mbox_files:
        mb = mailbox.mbox(mbox_file)
        for message in mb:
            msg_bytes = bytes(message)
            msg = BytesParser(policy=policy.default).parsebytes(msg_bytes)
            
            subject = str(msg.get("Subject", "(No Subject)"))
            sender = str(msg.get("From", "Unknown Sender"))
            date = str(msg.get("Date", "Unknown Date"))
            
            text_body = ""
            html_body = ""
            attachments_html = ""
            
            for part in msg.walk():
                if part.is_multipart():
                    continue
                    
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
                            attachments_html += f"<a href='attachments/{unique_attach_name}' target='_blank' style='display:inline-block; background:#e8eaed; padding:5px 10px; margin:2px; border-radius:4px; text-decoration:none; color:#1a73e8; font-size:12px;'>📎 {safe_attach_name}</a> "
                    except Exception:
                        pass
                else:
                    try:
                        if content_type == "text/plain" and not text_body:
                            text_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
                        elif content_type == "text/html" and not html_body:
                            html_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
                    except Exception:
                        pass
                        
            if html_body:
                final_html = html_body
                clean_text = re.sub(r'<[^>]+>', ' ', html_body)
            else:
                final_html = f"<pre style='font-family: Arial, sans-serif; white-space: pre-wrap;'>{text_body}</pre>"
                clean_text = text_body
                
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
                f.write(f"""<button onclick="window.print()" style="position:fixed; right:15px; top:15px; padding:8px 16px; background-color:#1a73e8; color:white; border:none; border-radius:4px; cursor:pointer; font-size:14px; font-weight:bold; z-index:1000;">Print / Save as PDF</button>""" + full_email_content)
            
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
                f"<strong>{subject}</strong>"
                f"<span class='dir'>{sender}<br>{date}</span><div style='clear:both;'></div></li>"
            )
            
            email_counter += 1

    js_search_data = json.dumps(search_data)

    html_header = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>MBOX Deep Search Viewer</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; display: flex; height: 100vh; overflow: hidden; color: #202124; background-color: #f8f9fa; }}
            #sidebar {{ width: 35%; padding: 20px; overflow-y: auto; background-color: #ffffff; border-right: 1px solid #dadce0; box-sizing: border-box; box-shadow: 2px 0 5px rgba(0,0,0,0.05); z-index: 10; }}
            #viewer-container {{ width: 65%; display: flex; flex-direction: column; background-color: #f1f3f4; }}
            #controls {{ padding: 12px 20px; background-color: #f1f3f4; border-bottom: 1px solid #dadce0; text-align: right; }}
            button {{ padding: 8px 16px; background-color: #1a73e8; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: bold; margin-left: 10px; }}
            button:hover {{ background-color: #1557b0; }}
            iframe {{ flex-grow: 1; border: none; width: 100%; height: 100%; background-color: #ffffff; }}
            h2 {{ color: #1a73e8; margin-top: 0; margin-bottom: 15px; font-size: 18px; }}
            #searchInput {{ width: 100%; padding: 10px; font-size: 14px; border: 1px solid #dadce0; border-radius: 4px; box-sizing: border-box; margin-bottom: 10px; }}
            ul {{ list-style-type: none; padding-left: 0; margin: 0; }}
            li {{ padding: 10px; background: #ffffff; margin-bottom: 6px; border-radius: 6px; border: 1px solid #e0e0e0; font-size: 13px; cursor: pointer; transition: background-color 0.2s, border-color 0.2s; }}
            li:hover {{ background-color: #e8f0fe; border-color: #d2e3fc; }}
            .dir {{ color: #5f6368; font-size: 0.85em; margin-top: 4px; display: block; word-break: break-all; }}
            .bulk-controls {{ margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid #dadce0; display: flex; justify-content: space-between; align-items: center; }}
        </style>
    </head>
    <body>
        <div id="sidebar">
            <h2>Legal MBOX Export Index</h2>
            <input type="text" id="searchInput" onkeyup="filterList()" placeholder="Search subjects, senders, or body content...">
            <div class="bulk-controls">
                <div>
                    <input type="checkbox" id="selectAll" onclick="toggleSelectAll()"> <label for="selectAll" style="font-size:13px; font-weight:bold;">Select All Visible</label>
                </div>
                <div style="font-size: 12px; color: #5f6368;" id="fileCount">Showing {email_counter} emails</div>
            </div>
            <ul id="fileList">
    """

    html_footer = f"""
            </ul>
        </div>
        <div id="viewer-container">
            <div id="controls">
                <button onclick="compileAndPrint()">Compile Selected to PDF / Print</button>
            </div>
            <iframe name="viewer" id="viewer" src="about:blank"></iframe>
        </div>
        <script>
            const searchData = {js_search_data};
            let selectedLi = null;
            
            function loadEmail(url, liElement) {{
                document.getElementById('viewer').src = url;
                if (selectedLi) {{
                    selectedLi.style.backgroundColor = "#ffffff";
                    selectedLi.style.borderColor = "#e0e0e0";
                }}
                liElement.style.backgroundColor = "#e8f0fe";
                liElement.style.borderColor = "#1a73e8";
                selectedLi = liElement;
            }}
            
            function filterList() {{
                const query = document.getElementById('searchInput').value.toLowerCase();
                const ul = document.getElementById('fileList');
                const items = ul.getElementsByTagName('li');
                let visibleCount = 0;
                
                for (let i = 0; i < items.length; i++) {{
                    const data = searchData[i];
                    const isMatch = data.name.toLowerCase().includes(query) || 
                                    data.content.toLowerCase().includes(query) ||
                                    data.sender.toLowerCase().includes(query);
                                    
                    if (isMatch) {{
                        items[i].style.display = "";
                        visibleCount++;
                    }} else {{
                        items[i].style.display = "none";
                        const cb = items[i].querySelector('.print-cb');
                        if(cb) cb.checked = false;
                    }}
                }}
                document.getElementById('fileCount').innerText = "Showing " + visibleCount + " emails";
                document.getElementById('selectAll').checked = false;
            }}

            function toggleSelectAll() {{
                const isChecked = document.getElementById('selectAll').checked;
                const items = document.querySelectorAll('.email-item');
                items.forEach(item => {{
                    if (item.style.display !== "none") {{
                        const cb = item.querySelector('.print-cb');
                        if (cb) cb.checked = isChecked;
                    }}
                }});
            }}

            function compileAndPrint() {{
                const checkboxes = document.querySelectorAll('.print-cb:checked');
                if (checkboxes.length === 0) {{
                    alert("Please select at least one email.");
                    return;
                }}

                let compiledHTML = "<!DOCTYPE html><html><head><title>Batch Export</title>";
                compiledHTML += "<style>@media print {{ .page-break {{ page-break-after: always; }} }}</style>";
                compiledHTML += "</head><body style='font-family: Arial, sans-serif;'>";

                checkboxes.forEach(cb => {{
                    const id = parseInt(cb.dataset.id);
                    const emailData = searchData.find(e => e.id === id);
                    if (emailData) {{
                        compiledHTML += emailData.html_payload;
                        compiledHTML += "<div class='page-break' style='border-bottom: 2px dashed #ccc; margin: 30px 0;'></div>";
                    }}
                }});

                compiledHTML += "</body></html>";

                const printWindow = window.open('', '_blank');
                printWindow.document.open();
                printWindow.document.write(compiledHTML);
                printWindow.document.close();
                printWindow.focus();

                setTimeout(() => {{
                    printWindow.print();
                }}, 750);
            }}
        </script>
    </body>
    </html>
    """

    final_content = html_header + "\n".join(list_items) + "\n" + html_footer

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(final_content)

    root.after(0, completion_callback, index_path)

def completion_callback(index_path):
    progress.stop()
    lbl_status.config(text="Opening Master Index...")
    webbrowser.open(f"file:///{index_path.replace(os.sep, '/')}")
    root.after(1000, sys.exit)

def on_closing():
    sys.exit()

root = tk.Tk()
root.title("Google Vault Extractor")
root.geometry("450x220")
root.eval('tk::PlaceWindow . center')
root.protocol("WM_DELETE_WINDOW", on_closing)

lbl_instruction = tk.Label(root, text="Select the folder containing your .mbox files.\nEmails will be indexed for bulk HTML compilation and PDF exporting.", wraplength=400, font=("Arial", 10))
lbl_instruction.pack(pady=20)

btn_browse = tk.Button(root, text="Browse...", command=select_folder, width=15, font=("Arial", 10, "bold"))
btn_browse.pack(pady=5)

progress = ttk.Progressbar(root, mode='indeterminate', length=300)
progress.pack(pady=15)

lbl_status = tk.Label(root, text="", font=("Arial", 9, "italic"), fg="#555555")
lbl_status.pack(pady=5)

root.mainloop()