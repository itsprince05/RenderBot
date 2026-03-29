import os
import shutil
import json
import time
from datetime import datetime, timedelta
from aiohttp import web
from config import BASE_DIR

IST_OFFSET = timedelta(hours=5, minutes=30)

async def check_auth(request):
    if request.cookies.get('auth') != 'true':
        raise web.HTTPFound('/login')
    if request.cookies.get('master_auth') != 'true':
        raise web.HTTPFound('/')

def get_safe_path(rel_path):
    if not rel_path:
        return BASE_DIR
    # Prevent directory traversal
    target = os.path.abspath(os.path.join(BASE_DIR, rel_path))
    if not target.startswith(BASE_DIR):
        return BASE_DIR
    return target

async def handle_files_page(request):
    await check_auth(request)
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ghost Catcher - Files</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
            body { margin: 0; padding: 0; background-color: #f0f2f5; color: #1c1e21; }
            .action-bar { 
                position: sticky; top: 0; z-index: 100; height: 56px; box-sizing: border-box;
                background: #2481cc; color: white; padding: 0 10px; gap: 10px;
                display: flex; align-items: center; justify-content: space-between;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2); 
            }
            .navbar-icon { width: 40px; height: 40px; border-radius: 50%; margin-right: 12px; border: 2px solid white; }
            .navbar-title { font-size: 20px; font-weight: 500; color: white; letter-spacing: 0.15px; }
            .container { padding: 15px; padding-bottom: 70px; max-width: 1200px; margin: 0 auto; }
            .fm-header { display: flex; justify-content: space-between; margin-bottom: 15px; align-items: center; flex-wrap: wrap; gap: 10px; }
            .path-bar { flex: 1; min-width: 250px; background: #fff; padding: 0 12px; border-radius: 8px; border: 1px solid #ccc; font-family: monospace; font-size: 14px; height: 38px; display: flex; align-items: center; box-sizing: border-box; }
            .btn { background: #2481cc; color: white; border: none; padding: 0 15px; border-radius: 6px; cursor: pointer; font-weight: 500; height: 38px; display: inline-flex; align-items: center; justify-content: center; box-sizing: border-box; }
            .btn:hover { background: #1a65a3; }
            .btn-danger { background: #fa5252; }
            .btn-danger:hover { background: #e03131; }
            .btn-secondary { background: #6c757d; }
            .action-btn { background: #3c94dd; color: white; border: none; width: 32px; height: 32px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; transition: background 0.15s; outline: none; padding: 0; flex-shrink: 0; }
            .action-btn:hover { background: #2f7bbc; }
            
            table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
            th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; vertical-align: middle; }
            th { background: #f8f9fa; font-weight: 600; color: #495057; }
            tr:hover { background: #f1f3f5; }
            tr.selected { background: #e3f2fd; }
            .icon { font-size: 18px; margin-right: 8px; vertical-align: middle; display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; flex-shrink: 0; }
            .icon svg { width: 48px; height: 48px; }
            .date-cell { font-size: 12px; color: #555; white-space: nowrap; }
            .date-cell .date-label { display: block; font-size: 11px; color: #999; font-weight: 500; }
            .sort-th { cursor: pointer; user-select: none; white-space: nowrap; }
            .sort-th:hover { background: #eef1f4; }
            .sort-th .sort-icon { display: inline-flex; align-items: center; vertical-align: middle; margin-left: 4px; opacity: 0.35; transition: opacity 0.15s, transform 0.2s; }
            .sort-th .sort-icon svg { width: 14px; height: 14px; }
            .sort-th.sort-active .sort-icon { opacity: 1; }
            .sort-th.sort-desc .sort-icon { transform: scaleY(-1); }
            @media (max-width: 768px) {
                .hide-mobile { display: none; }
                th, td { padding: 10px 8px; font-size: 13px; }
            }
            .clickable { cursor: pointer; color: #2481cc; font-weight: 500; display:flex; align-items:center; }
            .clickable:hover { text-decoration: underline; }
            
            .clickable-path { cursor: pointer; color: #2481cc; font-weight: 500; transition: color 0.15s; text-decoration: none; }
            .clickable-path:hover { color: #1a65a3; text-decoration: underline; }
            
            #editorModal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 100; padding: 20px; }
            .modal-content { background: #fff; width: 100%; max-width: 900px; margin: 0 auto; border-radius: 8px; display: flex; flex-direction: column; height: 100%; max-height: 90vh; }
            .modal-header { padding: 15px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
            .modal-body { flex: 1; padding: 15px; display: flex; flex-direction: column; overflow: hidden;}
            textarea { flex: 1; width: 100%; resize: none; border: 1px solid #ccc; border-radius: 4px; padding: 10px; font-family: monospace; font-size: 14px; outline: none;}
            .modal-footer { padding: 15px; border-top: 1px solid #eee; display: flex; justify-content: flex-end; gap: 10px; }
            
            .action-links span { margin-right: 15px; cursor: pointer; color: #2481cc; background: #e3f2fd; padding: 6px 10px; border-radius: 8px; font-weight:500; font-size:14px; display:inline-flex; align-items:center; gap: 4px; transition: background 0.2s;}
            .action-links span:hover { background: #cce4f7; text-decoration: none; }
            .action-links .del-btn { color: #e53935; background: #ffebee; }
            .action-links .del-btn:hover { background: #ffcdd2; text-decoration: none; }
            
            .btn-icon { display:inline-flex; align-items:center; gap: 6px; }
            .btn-icon svg { width: 18px; height: 18px; }
            .file-thumb { width: 48px; height: 48px; border-radius: 6px; object-fit: cover; vertical-align: middle; margin-right: 8px; background: #f0f2f5; flex-shrink: 0; }
            .vid-thumb-wrap { position: relative; display: inline-flex; width: 48px; height: 48px; margin-right: 8px; flex-shrink: 0; vertical-align: middle; }
            .vid-thumb-wrap video { width: 48px; height: 48px; border-radius: 6px; object-fit: cover; background: #000; }
            .vid-thumb-wrap .play-overlay { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 20px; height: 20px; background: rgba(0,0,0,0.55); border-radius: 50%; display: flex; align-items: center; justify-content: center; pointer-events: none; }
            .vid-thumb-wrap .play-overlay svg { width: 12px; height: 12px; fill: white; stroke: white; }
            .cb-cell { width: 36px; text-align: center; cursor: pointer; }
            .cb-cell svg { width: 22px; height: 22px; vertical-align: middle; }
            .select-bar { position: fixed; bottom: 0; left: 0; right: 0; background: #333; color: white; padding: 12px 20px; display: none; align-items: center; justify-content: space-between; z-index: 200; font-size: 14px; font-weight: 500; }
            .select-bar .del-sel-btn { background: #fa5252; color: white; border: none; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px; }
            .select-bar .del-sel-btn:hover { background: #e03131; }
            .select-bar .cancel-sel-btn { background: rgba(255,255,255,0.2); color: white; border: none; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-weight: 500; font-size: 14px; }
            
            .grid-container { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; padding: 5px 0; padding-bottom: 60px; }
            @media (max-width: 768px) { .grid-container { grid-template-columns: repeat(2, 1fr); } }
            .grid-card { background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); cursor: pointer; position: relative; transition: box-shadow 0.2s; }
            .grid-card:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.15); }
            .grid-card.selected { outline: 3px solid #0ca678; }
            .grid-thumb { width: 100%; aspect-ratio: 1; object-fit: cover; background: #f0f2f5; display: block; }
            .grid-icon-box { width: 100%; aspect-ratio: 1; background: #ffffff; display: flex; align-items: center; justify-content: center; }
            .grid-icon-box svg { width: 60px; height: 60px; }
            .grid-vid-wrap { width: 100%; aspect-ratio: 1; position: relative; background: #000; }
            .grid-vid-wrap video { width: 100%; height: 100%; object-fit: cover; }
            .grid-vid-wrap .play-overlay { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 36px; height: 36px; background: rgba(0,0,0,0.55); border-radius: 50%; display: flex; align-items: center; justify-content: center; pointer-events: none; }
            .grid-vid-wrap .play-overlay svg { width: 18px; height: 18px; fill: white; stroke: white; }
            .grid-info { padding: 8px 10px; display: flex; flex-direction: row; align-items: center; gap: 6px; }
            .grid-name { flex: 1; font-size: 11px; font-weight: 500; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
            .grid-cb { flex-shrink: 0; cursor: pointer; }
            .grid-cb svg { width: 20px; height: 20px; vertical-align: middle; }
            .view-toggle-btn { background: none; border: none; cursor: pointer; color: white; padding: 8px; display: inline-flex; align-items: center; justify-content: center; border-radius: 6px; transition: background 0.15s; }
            .view-toggle-btn:hover { background: rgba(255,255,255,0.15); }
        </style>
    </head>
    <body>
        <div class="action-bar">
            <div style="display: flex; align-items: center;">
                <img src="https://princeapps.com/telegram/ghost.png?v=2" class="navbar-icon" alt="Logo">
                <div class="navbar-title">Ghost Catcher</div>
            </div>
            <div style="display:flex; align-items:center; gap:6px;">
                 <button class="view-toggle-btn" id="viewToggleBtn" onclick="toggleViewMode()" title="Toggle View">
                     <svg id="viewIcon" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/></svg>
                 </button>
                 <button class="action-btn" onclick="window.location.href='/'" title="Back to Main">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/></svg>
                 </button>
            </div>
        </div>
        
        <div class="container">
            <div class="fm-header">
                <button class="btn btn-secondary btn-icon" onclick="goUp()" title="Up">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-left-icon lucide-arrow-left"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>
                </button>
                <div class="path-bar" id="current_path">/</div>
                <div style="display:flex; gap:10px;">
                    <button class="btn btn-icon" onclick="openCreateMenu()" title="New">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-circle-plus-icon lucide-circle-plus"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/><path d="M12 8v8"/></svg>
                    </button>
                    <input type="file" id="fileUpload" style="display:none;" onchange="uploadFile(this)">
                    <button class="btn btn-icon" onclick="document.getElementById('fileUpload').click()" title="Upload">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-up-to-line-icon lucide-arrow-up-to-line"><path d="M5 3h14"/><path d="m18 13-6-6-6 6"/><path d="M12 7v14"/></svg>
                    </button>
                </div>
            </div>
            
            <table id="files_table">
                <thead>
                    <tr>
                        <th class="cb-cell" id="select-all-th" onclick="toggleSelectAll()" style="cursor:pointer;"></th>
                        <th>Name</th>
                        <th class="sort-th" id="sort-size" onclick="toggleSort('size')">Size <span class="sort-icon"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="m21 8-4-4-4 4"/><path d="M17 4v16"/></svg></span></th>
                        <th class="sort-th hide-mobile" id="sort-modified" onclick="toggleSort('modified')">Modified <span class="sort-icon"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="m21 8-4-4-4 4"/><path d="M17 4v16"/></svg></span></th>
                        <th class="sort-th hide-mobile" id="sort-created" onclick="toggleSort('created')">Created <span class="sort-icon"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="m21 8-4-4-4 4"/><path d="M17 4v16"/></svg></span></th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="files_list"></tbody>
            </table>
            <div id="grid_view" class="grid-container" style="display:none;"></div>
            <div class="select-bar" id="selectBar">
                <span id="selectCount">0 selected</span>
                <div>
                    <button class="cancel-sel-btn" onclick="selectAllItems()">Select All</button>
                    <button class="del-sel-btn" onclick="deleteSelected()">Delete Selected</button>
                    <button class="cancel-sel-btn" onclick="clearSelection()">Cancel</button>
                </div>
            </div>
        </div>
        
        <!-- Editor Modal -->
        <div id="editorModal">
            <div class="modal-content">
                <div class="modal-header">
                    <span id="editorTitle">Edit File</span>
                    <button class="btn btn-secondary btn-icon" onclick="closeEditor()" style="padding:4px 8px;">✕</button>
                </div>
                <div class="modal-body">
                    <textarea id="editorText"></textarea>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary btn-icon" onclick="closeEditor()">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-circle-x-icon lucide-circle-x"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>                    
                        Cancel
                    </button>
                    <button class="btn btn-icon" onclick="saveFile()">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check-icon lucide-check"><path d="M20 6 9 17l-5-5"/></svg>
                        Save
                    </button>
                </div>
            </div>
        </div>

        <script>
            let currentPath = "";
            let editingFile = "";
            let currentFiles = [];
            let sortColumn = null;
            let sortAsc = true;
            let selectedPaths = new Set();
            let viewMode = 'list';
            
            const SVG_LIST_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 5h.01"/><path d="M3 12h.01"/><path d="M3 19h.01"/><path d="M8 5h13"/><path d="M8 12h13"/><path d="M8 19h13"/></svg>`;
            const SVG_GRID_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/></svg>`;
            
            const SVG_FOLDER = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>`;
            const SVG_JSON = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#2481cc" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M10 12a1 1 0 0 0-1 1v1a1 1 0 0 1-1 1 1 1 0 0 1 1 1v1a1 1 0 0 0 1 1"/><path d="M14 18a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1 1 1 0 0 1-1-1v-1a1 1 0 0 0-1-1"/></svg>`;
            const SVG_TXT = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#4b5563" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>`;
            const SVG_UNKNOWN = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/></svg>`;
            const SVG_CODE = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 16 4-4-4-4"/><path d="m6 8-4 4 4 4"/><path d="m14.5 4-5 16"/></svg>`;
            const SVG_IMAGE = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>`;
            const SVG_VIDEO = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M3 7.5h4"/><path d="M3 12h18"/><path d="M3 16.5h4"/><path d="M17 3v18"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/></svg>`;
            const SVG_AUDIO = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/></svg>`;
            const SVG_DOWNLOAD = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17V3"/><path d="m6 11 6 6 6-6"/><path d="M19 21H5"/></svg>`;
            const SVG_DELETE = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 11v6"/><path d="M14 11v6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`;
            const SVG_CB_OFF = `<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#aaa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/></svg>`;
            const SVG_CB_ON = `<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0ca678" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10.656V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12.344"/><path d="m9 11 3 3L22 4"/></svg>`;
            const SVG_PLAY = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="white" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg>`;

            function isImageFile(name) {
                const exts = ['.png','.jpg','.jpeg','.webp','.gif','.bmp'];
                const l = name.toLowerCase();
                return exts.some(e => l.endsWith(e));
            }
            function isVideoFile(name) {
                const exts = ['.mp4','.mkv','.avi','.mov','.webm','.flv','.oga'];
                const l = name.toLowerCase();
                return exts.some(e => l.endsWith(e));
            }
            function isAudioFile(name) {
                const exts = ['.mp3','.ogg','.wav','.m4a','.flac','.aac','.oga'];
                const l = name.toLowerCase();
                return exts.some(e => l.endsWith(e));
            }
            function isMediaFile(name) {
                return isImageFile(name) || isVideoFile(name) || isAudioFile(name) || name.toLowerCase().endsWith('.svg');
            }

            function getFileIcon(name, isDir) {
                if(isDir) return SVG_FOLDER;
                const low = name.toLowerCase();
                if(low.endsWith('.json')) return SVG_JSON;
                if(low.endsWith('.txt')) return SVG_TXT;
                
                const codeExts = ['.py', '.js', '.html', '.css', '.php', '.xml', '.ts', '.java', '.c', '.cpp', '.h', '.sh'];
                for(let e of codeExts) { if(low.endsWith(e)) return SVG_CODE; }
                
                const imgExts = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg'];
                for(let e of imgExts) { if(low.endsWith(e)) return SVG_IMAGE; }
                
                const vidExts = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv'];
                for(let e of vidExts) { if(low.endsWith(e)) return SVG_VIDEO; }
                
                const audExts = ['.mp3', '.ogg', '.wav', '.m4a', '.flac', '.aac'];
                for(let e of audExts) { if(low.endsWith(e)) return SVG_AUDIO; }
                
                return SVG_UNKNOWN;
            }
            
            function handleImgError(el, mode) {
                const fallback = document.createElement('span');
                if (mode === 'grid') {
                    fallback.className = 'grid-icon-box';
                } else {
                    fallback.className = 'icon';
                }
                fallback.innerHTML = SVG_IMAGE;
                el.replaceWith(fallback);
            }

            async function loadPath(path) {
                currentPath = path;
                
                let parts = path.split('/').filter(p => p.trim() !== "");
                let rootIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-house-icon lucide-house" style="margin-right:4px;"><path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>`;
                let bHtml = `<span class="clickable-path" onclick="loadPath('')" title="Root" style="display:inline-flex; align-items:center;">${rootIcon} Root</span>`;
                let bPath = "";
                for(let i=0; i<parts.length; i++) {
                    bPath += (i === 0 ? "" : "/") + parts[i];
                    bHtml += ` / <span class="clickable-path" onclick="loadPath('${bPath}')">${parts[i]}</span>`;
                }
                document.getElementById("current_path").innerHTML = bHtml;
                try {
                    const res = await fetch(`/api/fm/list?path=${encodeURIComponent(path)}`);
                    const data = await res.json();
                    if (!data.success) { alert(data.error); return; }
                    currentFiles = data.files;
                    sortColumn = null;
                    sortAsc = true;
                    updateSortHeaders();
                    renderCurrentView();
                } catch(e) {
                    console.error('Error loading files:', e);
                }
            }
            
            function updateSortHeaders() {
                ['size', 'modified', 'created'].forEach(col => {
                    const th = document.getElementById('sort-' + col);
                    if (!th) return;
                    th.classList.remove('sort-active', 'sort-desc');
                    if (sortColumn === col) {
                        th.classList.add('sort-active');
                        if (!sortAsc) th.classList.add('sort-desc');
                    }
                });
            }
            
            function toggleSort(col) {
                if (sortColumn === col) {
                    sortAsc = !sortAsc;
                } else {
                    sortColumn = col;
                    sortAsc = true;
                }
                updateSortHeaders();
                renderCurrentView();
            }
            
            function renderCurrentView() {
                if (viewMode === 'grid') {
                    document.getElementById('files_table').style.display = 'none';
                    document.getElementById('grid_view').style.display = 'grid';
                    renderGridView(currentFiles);
                } else {
                    document.getElementById('files_table').style.display = 'table';
                    document.getElementById('grid_view').style.display = 'none';
                    renderFiles(currentFiles);
                }
            }
            
            function toggleViewMode() {
                viewMode = viewMode === 'list' ? 'grid' : 'list';
                const icon = document.getElementById('viewIcon');
                if (viewMode === 'grid') {
                    icon.outerHTML = SVG_LIST_ICON.replace('<svg ', '<svg id="viewIcon" ');
                } else {
                    icon.outerHTML = SVG_GRID_ICON.replace('<svg ', '<svg id="viewIcon" ');
                }
                selectedPaths.clear();
                updateSelectBar();
                renderCurrentView();
            }
            
            function renderFiles(files) {
                const tbody = document.getElementById("files_list");
                tbody.innerHTML = "";
                selectedPaths.clear();
                updateSelectBar();
                
                const dirs = files.filter(f => f.is_dir);
                const onlyFiles = files.filter(f => !f.is_dir);
                dirs.sort((a, b) => a.name.localeCompare(b.name));
                
                if (sortColumn) {
                    onlyFiles.sort((a, b) => {
                        let va, vb;
                        if (sortColumn === 'size') { va = a.size || 0; vb = b.size || 0; }
                        else if (sortColumn === 'modified') { va = a.mtime_ts || 0; vb = b.mtime_ts || 0; }
                        else if (sortColumn === 'created') { va = a.ctime_ts || 0; vb = b.ctime_ts || 0; }
                        let result = va - vb;
                        if (result === 0) result = a.name.localeCompare(b.name);
                        return sortAsc ? result : -result;
                    });
                } else {
                    onlyFiles.sort((a, b) => a.name.localeCompare(b.name));
                }
                
                const sorted = [...dirs, ...onlyFiles];
                
                sorted.forEach(f => {
                    const tr = document.createElement("tr");
                    const targetPath = currentPath ? currentPath + "/" + f.name : f.name;
                    tr.dataset.path = targetPath;
                    tr.dataset.isDir = f.is_dir ? '1' : '0';
                    const icon = getFileIcon(f.name, f.is_dir);
                    
                    // Checkbox cell
                    const cbTd = document.createElement("td");
                    cbTd.className = "cb-cell";
                    cbTd.innerHTML = SVG_CB_OFF;
                    cbTd.onclick = (e) => { e.stopPropagation(); toggleSelect(tr, targetPath); };
                    tr.appendChild(cbTd);
                    
                    // Name cell
                    const nameTd = document.createElement("td");
                    const nameSpan = document.createElement("span");
                    nameSpan.className = "clickable";
                    
                    if (!f.is_dir && isImageFile(f.name)) {
                        nameSpan.innerHTML = `<img class="file-thumb" loading="lazy" src="/api/fm/download?path=${encodeURIComponent(targetPath)}&inline=1" onerror="handleImgError(this,'list')"> ${f.name}`;
                    } else if (!f.is_dir && isVideoFile(f.name)) {
                        nameSpan.innerHTML = `<span class="vid-thumb-wrap"><video src="/api/fm/download?path=${encodeURIComponent(targetPath)}&inline=1" preload="none" muted></video><span class="play-overlay">${SVG_PLAY}</span></span> ${f.name}`;
                    } else {
                        nameSpan.innerHTML = `<span class="icon">${icon}</span> ${f.name}`;
                    }
                    
                    nameSpan.onclick = () => {
                        const newPath = targetPath;
                        if (f.is_dir) {
                            loadPath(newPath);
                        } else if (isMediaFile(f.name)) {
                            openMediaEmbed(newPath, f.name);
                        } else {
                            openFile(newPath);
                        }
                    };
                    nameTd.appendChild(nameSpan);
                    
                    const sizeTd = document.createElement("td");
                    let sizeStr = "-";
                    if (!f.is_dir) {
                        sizeStr = f.size >= 1048576 ? (f.size / 1048576).toFixed(1) + " MB" : (f.size / 1024).toFixed(1) + " KB";
                    }
                    sizeTd.innerText = sizeStr;
                    
                    const modTd = document.createElement("td");
                    modTd.className = "date-cell hide-mobile";
                    modTd.innerHTML = f.modified_at || "-";
                    
                    const creTd = document.createElement("td");
                    creTd.className = "date-cell hide-mobile";
                    creTd.innerHTML = f.created_at || "-";
                    
                    const actionTd = document.createElement("td");
                    actionTd.className = "action-links";
                    actionTd.innerHTML = `<span title="Delete" class="del-btn" onclick="event.stopPropagation(); deleteItem('${targetPath}', ${f.is_dir})">${SVG_DELETE}</span>`;
                    if (!f.is_dir) {
                        actionTd.innerHTML += `<span title="Download" onclick="event.stopPropagation(); downloadFile('${targetPath}')">${SVG_DOWNLOAD}</span>`;
                    }
                    
                    tr.appendChild(nameTd);
                    tr.appendChild(sizeTd);
                    tr.appendChild(modTd);
                    tr.appendChild(creTd);
                    tr.appendChild(actionTd);
                    tbody.appendChild(tr);
                });
            }
            
            function toggleSelect(tr, path) {
                if (selectedPaths.has(path)) {
                    selectedPaths.delete(path);
                    tr.classList.remove('selected');
                    tr.querySelector('.cb-cell').innerHTML = SVG_CB_OFF;
                } else {
                    selectedPaths.add(path);
                    tr.classList.add('selected');
                    tr.querySelector('.cb-cell').innerHTML = SVG_CB_ON;
                }
                updateSelectBar();
            }
            
            function toggleSelectAll() {
                const rows = document.querySelectorAll('#files_list tr');
                if (selectedPaths.size === rows.length && rows.length > 0) {
                    clearSelection();
                } else {
                    rows.forEach(tr => {
                        const p = tr.dataset.path;
                        if (!selectedPaths.has(p)) {
                            selectedPaths.add(p);
                            tr.classList.add('selected');
                            tr.querySelector('.cb-cell').innerHTML = SVG_CB_ON;
                        }
                    });
                    updateSelectBar();
                }
            }
            
            function clearSelection() {
                selectedPaths.clear();
                document.querySelectorAll('#files_list tr').forEach(tr => {
                    tr.classList.remove('selected');
                    tr.querySelector('.cb-cell').innerHTML = SVG_CB_OFF;
                });
                updateSelectBar();
            }
            
            function updateSelectBar() {
                const bar = document.getElementById('selectBar');
                const count = selectedPaths.size;
                bar.style.display = 'flex';
                document.getElementById('selectCount').textContent = count > 0 ? count + ' selected' : '';
            }
            
            function selectAllItems() {
                if (viewMode === 'grid') {
                    const cards = document.querySelectorAll('#grid_view .grid-card');
                    cards.forEach(card => {
                        const p = card.dataset.path;
                        if (!selectedPaths.has(p)) {
                            selectedPaths.add(p);
                            card.classList.add('selected');
                            card.querySelector('.grid-cb').innerHTML = SVG_CB_ON;
                        }
                    });
                } else {
                    const rows = document.querySelectorAll('#files_list tr');
                    rows.forEach(tr => {
                        const p = tr.dataset.path;
                        if (!selectedPaths.has(p)) {
                            selectedPaths.add(p);
                            tr.classList.add('selected');
                            tr.querySelector('.cb-cell').innerHTML = SVG_CB_ON;
                        }
                    });
                }
                updateSelectBar();
            }
            
            async function deleteSelected() {
                if (!selectedPaths.size) return;
                if (!confirm(`Delete ${selectedPaths.size} selected item(s)?`)) return;
                const paths = [...selectedPaths];
                try {
                    for (const p of paths) {
                        await fetch('/api/fm/delete', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ path: p })
                        });
                    }
                    selectedPaths.clear();
                    updateSelectBar();
                    setTimeout(() => loadPath(currentPath), 300);
                } catch(e) { alert('Error deleting selected items'); }
            }
            
            function openMediaEmbed(path, name) {
                const url = `/api/fm/download?path=${encodeURIComponent(path)}&inline=1`;
                const low = name.toLowerCase();
                let content;
                if (isVideoFile(name)) {
                    content = `<video src="${url}" controls autoplay style="max-width:100%;max-height:90vh;"></video>`;
                } else if (isAudioFile(name)) {
                    content = `<div style="padding:40px;text-align:center;"><p style="margin-bottom:20px;font-size:18px;font-weight:600;">${name}</p><audio src="${url}" controls autoplay style="width:100%;max-width:500px;"></audio></div>`;
                } else {
                    // image or svg
                    content = `<img src="${url}" style="max-width:100%;max-height:90vh;">`;
                }
                const html = `<!DOCTYPE html><html><head><title>${name}</title><style>body{margin:0;background:#000;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:sans-serif;color:#fff;}</style></head><body>${content}</body></html>`;
                const w = window.open('', '_blank');
                w.document.write(html);
                w.document.close();
            }
            
            function renderGridView(files) {
                const grid = document.getElementById('grid_view');
                grid.innerHTML = '';
                selectedPaths.clear();
                updateSelectBar();
                
                const dirs = files.filter(f => f.is_dir);
                const onlyFiles = files.filter(f => !f.is_dir);
                dirs.sort((a, b) => a.name.localeCompare(b.name));
                onlyFiles.sort((a, b) => a.name.localeCompare(b.name));
                const sorted = [...dirs, ...onlyFiles];
                
                sorted.forEach(f => {
                    const targetPath = currentPath ? currentPath + '/' + f.name : f.name;
                    const card = document.createElement('div');
                    card.className = 'grid-card';
                    card.dataset.path = targetPath;
                    
                    let thumbHtml;
                    if (!f.is_dir && isImageFile(f.name)) {
                        thumbHtml = `<img class="grid-thumb" loading="lazy" src="/api/fm/download?path=${encodeURIComponent(targetPath)}&inline=1" onerror="handleImgError(this,'grid')">`;
                    } else if (!f.is_dir && isVideoFile(f.name)) {
                        thumbHtml = `<div class="grid-vid-wrap"><video src="/api/fm/download?path=${encodeURIComponent(targetPath)}&inline=1" preload="none" muted></video><span class="play-overlay">${SVG_PLAY}</span></div>`;
                    } else {
                        const icon = getFileIcon(f.name, f.is_dir);
                        thumbHtml = `<div class="grid-icon-box">${icon}</div>`;
                    }
                    
                    const safePath = targetPath.replace(/'/g, "\\'");
                    card.innerHTML = `${thumbHtml}<div class="grid-info" onclick="event.stopPropagation(); gridToggleSelect(this.closest('.grid-card'), '${safePath}')"><span class="grid-cb"></span><span class="grid-name" title="${f.name}">${f.name}</span></div>`;
                    card.querySelector('.grid-cb').innerHTML = SVG_CB_OFF;
                    
                    card.onclick = () => {
                        if (f.is_dir) {
                            loadPath(targetPath);
                        } else if (isMediaFile(f.name)) {
                            openMediaEmbed(targetPath, f.name);
                        } else {
                            openFile(targetPath);
                        }
                    };
                    
                    grid.appendChild(card);
                });
            }
            
            function gridToggleSelect(card, path) {
                if (selectedPaths.has(path)) {
                    selectedPaths.delete(path);
                    card.classList.remove('selected');
                    card.querySelector('.grid-cb').innerHTML = SVG_CB_OFF;
                } else {
                    selectedPaths.add(path);
                    card.classList.add('selected');
                    card.querySelector('.grid-cb').innerHTML = SVG_CB_ON;
                }
                updateSelectBar();
            }
            
            function goUp() {
                if (!currentPath) return;
                const parts = currentPath.split('/');
                parts.pop();
                loadPath(parts.join('/'));
            }
            
            async function openFile(path) {
                try {
                    const res = await fetch(`/api/fm/read?path=${encodeURIComponent(path)}`);
                    const data = await res.json();
                    if (!data.success) { alert(data.error || "Cannot edit this file"); return; }
                    editingFile = path;
                    document.getElementById("editorTitle").innerText = "Editing: " + path;
                    document.getElementById("editorText").value = data.content;
                    document.getElementById("editorModal").style.display = "flex";
                } catch(e) { alert("Error reading file"); }
            }
            
            async function saveFile() {
                const content = document.getElementById("editorText").value;
                try {
                    const res = await fetch(`/api/fm/write`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ path: editingFile, content: content })
                    });
                    const data = await res.json();
                    if(data.success) {
                        closeEditor();
                        loadPath(currentPath);
                    } else alert(data.error);
                } catch(e) { alert("Error saving file"); }
            }
            
            function closeEditor() {
                document.getElementById("editorModal").style.display = "none";
                editingFile = "";
                document.getElementById("editorText").value = "";
            }
            
            async function deleteItem(path, isDir) {
                const msg = isDir ? "Delete this folder and ALL its contents?" : "Delete this file?";
                if(!confirm(msg)) return;
                try {
                    const res = await fetch(`/api/fm/delete`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ path: path })
                    });
                    const data = await res.json();
                    if(data.success) setTimeout(() => loadPath(currentPath), 300);
                    else alert(data.error);
                } catch(e) { alert("Error deleting"); }
            }
            
            function downloadFile(path) {
                window.location.href = `/api/fm/download?path=${encodeURIComponent(path)}`;
            }
            
            async function openCreateMenu() {
                const name = prompt("Enter new file/folder name (end with / for folder):");
                if(!name) return;
                try {
                    const res = await fetch(`/api/fm/create`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ path: currentPath ? currentPath + "/" + name : name })
                    });
                    const data = await res.json();
                    if(data.success) loadPath(currentPath);
                    else alert(data.error);
                } catch(e) { alert("Error creating"); }
            }
            
            async function uploadFile(input) {
                if(!input.files.length) return;
                const file = input.files[0];
                const formData = new FormData();
                formData.append("file", file);
                formData.append("path", currentPath);
                
                try {
                    const res = await fetch(`/api/fm/upload`, { method: 'POST', body: formData });
                    const data = await res.json();
                    if(data.success) loadPath(currentPath);
                    else alert(data.error);
                } catch(e) { alert("Upload error"); }
                input.value = "";
            }
            
            // Initial load
            const urlParams = new URLSearchParams(window.location.search);
            const initialPath = urlParams.get('path') || "";
            loadPath(initialPath);
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def api_fm_list(request):
    await check_auth(request)
    rel_path = request.query.get('path', '')
    target = get_safe_path(rel_path)
    if not os.path.exists(target):
        return web.json_response({"success": False, "error": "Path not found"})
        
    try:
        files = []
        for name in os.listdir(target):
            p = os.path.join(target, name)
            is_dir = os.path.isdir(p)
            size = os.path.getsize(p) if not is_dir else 0
            try:
                stat = os.stat(p)
                mtime_ts = stat.st_mtime
                ctime_ts = stat.st_ctime
                mtime = datetime.utcfromtimestamp(mtime_ts) + IST_OFFSET
                ctime = datetime.utcfromtimestamp(ctime_ts) + IST_OFFSET
                modified_at = mtime.strftime('%I:%M %p %d/%m/%Y').lstrip('0')
                created_at = ctime.strftime('%I:%M %p %d/%m/%Y').lstrip('0')
            except Exception:
                modified_at = "-"
                created_at = "-"
                mtime_ts = 0
                ctime_ts = 0
            files.append({"name": name, "is_dir": is_dir, "size": size, "modified_at": modified_at, "created_at": created_at, "mtime_ts": mtime_ts, "ctime_ts": ctime_ts})
        return web.json_response({"success": True, "files": files})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def api_fm_read(request):
    await check_auth(request)
    rel_path = request.query.get('path', '')
    target = get_safe_path(rel_path)
    if not os.path.isfile(target):
        return web.json_response({"success": False, "error": "File not found"})
        
    try:
        with open(target, 'r', encoding='utf-8') as f:
            content = f.read()
        return web.json_response({"success": True, "content": content})
    except UnicodeDecodeError:
        return web.json_response({"success": False, "error": "File is binary, cannot edit as text."})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def api_fm_write(request):
    await check_auth(request)
    data = await request.json()
    rel_path = data.get('path', '')
    content = data.get('content', '')
    target = get_safe_path(rel_path)
    
    try:
        with open(target, 'w', encoding='utf-8') as f:
            f.write(content)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def api_fm_delete(request):
    await check_auth(request)
    data = await request.json()
    rel_path = data.get('path', '')
    target = get_safe_path(rel_path)
    # Don't allow deleting base directory itself
    if target == BASE_DIR:
        return web.json_response({"success": False, "error": "Cannot delete root."})
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def api_fm_create(request):
    await check_auth(request)
    data = await request.json()
    rel_path = data.get('path', '')
    if not rel_path:
        return web.json_response({"success": False, "error": "Invalid name"})
        
    target = get_safe_path(rel_path)
    is_dir = rel_path.endswith('/')
    
    try:
        if is_dir:
            os.makedirs(target, exist_ok=True)
        else:
            # Ensure parent exists
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'w') as f: pass
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def api_fm_upload(request):
    await check_auth(request)
    reader = await request.multipart()
    path = ""
    file_field = None
    
    while True:
        field = await reader.next()
        if not field: break
        if field.name == 'path':
            path = await field.read()
            path = path.decode('utf-8')
        elif field.name == 'file':
            filename = field.filename
            target = get_safe_path(os.path.join(path, filename))
            with open(target, 'wb') as f:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk: break
                    f.write(chunk)
            
    return web.json_response({"success": True})

async def api_fm_download(request):
    await check_auth(request)
    rel_path = request.query.get('path', '')
    target = get_safe_path(rel_path)
    if not os.path.isfile(target):
        return web.Response(status=404, text="File not found")
        
    filename = os.path.basename(target)
    inline = request.query.get('inline') == '1'
    disposition = "inline" if inline else "attachment"
    
    return web.FileResponse(target, headers={
        "Content-Disposition": f'{disposition}; filename="{filename}"'
    })

def register_fm_routes(app):
    app.router.add_get('/files', handle_files_page)
    app.router.add_get('/api/fm/list', api_fm_list)
    app.router.add_get('/api/fm/read', api_fm_read)
    app.router.add_post('/api/fm/write', api_fm_write)
    app.router.add_post('/api/fm/delete', api_fm_delete)
    app.router.add_post('/api/fm/create', api_fm_create)
    app.router.add_post('/api/fm/upload', api_fm_upload)
    app.router.add_get('/api/fm/download', api_fm_download)
