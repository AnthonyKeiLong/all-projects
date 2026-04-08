// Global State
let students = [];
let localRecords = [];

// DOM Elements
const classListInput = document.getElementById('class-list-input');
const assignmentInput = document.getElementById('assignment-name');
const studentGrid = document.getElementById('student-grid');
const emptyState = document.getElementById('empty-state');
const statsCounter = document.getElementById('stats-counter');
const outputMessage = document.getElementById('output-message');
const outputAbsent = document.getElementById('output-absent');

// ==========================================
// Helper: File Name Generation with Timestamp
// ==========================================
const getFormattedFileName = (extension, suffix = '') => {
    const now = new Date();
    const dd = String(now.getDate()).padStart(2, '0');
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const yyyy = now.getFullYear();
    const hh = String(now.getHours()).padStart(2, '0');
    const min = String(now.getMinutes()).padStart(2, '0');
    
    let hwName = assignmentInput.value.trim();
    hwName = hwName ? hwName.replace(/[^a-zA-Z0-9\u4e00-\u9fa5]/g, '_') : 'Unnamed_Assignment';
    hwName = hwName.replace(/_+/g, '_').replace(/_+$/, ''); 

    let fileName = `${dd}${mm}${yyyy}_${hh}_${min}_${hwName}`;
    if (suffix) {
        fileName += `_${suffix}`;
    }
    
    return `${fileName}.${extension}`;
};

// ==========================================
// Helper: Save File Dialog (File System Access API)
// ==========================================
const saveFileWithDialog = async (blob, defaultFileName, fileTypeOptions) => {
    try {
        if (window.showSaveFilePicker) {
            const handle = await window.showSaveFilePicker({
                suggestedName: defaultFileName,
                types: [fileTypeOptions]
            });
            const writable = await handle.createWritable();
            await writable.write(blob);
            await writable.close();
        } else {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = defaultFileName;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            console.error("Save failed:", err);
            alert("Failed to save the file. See console for details.");
        }
    }
};

// ==========================================
// Core Logic & Demo Functions
// ==========================================

window.loadDemoClass = () => {
    const demoData = `1 Alice Smith
2 Bob Johnson
3 Charlie Williams
4 Diana Brown
5 Ethan Jones
6 Fiona Garcia
7 George Martinez
8 Hannah Rodriguez
9 Ian Lee
10 Julia Perez
11 Kevin White
12 Liam Harris
13 Mia Clark
14 Noah Lewis
15 Olivia Robinson
16 Peter Walker
17 Quinn Hall
18 Rachel Allen
19 Samuel Young
20 Taylor King`;
    classListInput.value = demoData;
    assignmentInput.value = "Chapter 4 Math Test";
    window.parseInput();
    window.updateOutput();
};

window.parseInput = () => {
    const text = classListInput.value;
    const lines = text.split('\n');
    students = [];

    lines.forEach(line => {
        const match = line.match(/^(\d+)\s+(.+)$/);
        if (match) {
            students.push({
                classNum: match[1],
                name: match[2].trim(),
                status: 'present' 
            });
        }
    });

    window.renderGrid();
};

window.renderGrid = () => {
    studentGrid.innerHTML = '';
    
    if (students.length === 0) {
        emptyState.classList.remove('hidden');
        studentGrid.classList.add('hidden');
        statsCounter.innerText = `0 Students`;
    } else {
        emptyState.classList.add('hidden');
        studentGrid.classList.remove('hidden');
        statsCounter.innerText = `${students.length} Students`;
    }

    students.forEach((student, index) => {
        const btn = document.createElement('button');
        btn.className = 'grid-item h-20 rounded-xl flex flex-col items-center justify-center p-2 text-sm transition-all duration-200 border-2 font-medium relative shadow-sm overflow-hidden group';
        
        if (student.status === 'present') {
            btn.classList.add('bg-white', 'border-slate-200', 'hover:border-indigo-300', 'hover:shadow-md');
            btn.innerHTML = `
                <span class="text-slate-400 font-mono text-xs mb-1">#${student.classNum}</span>
                <span class="text-slate-700 text-center w-full truncate px-1">${student.name}</span>
            `;
        } else if (student.status === 'missing') {
            btn.classList.add('bg-red-50', 'border-red-400', 'shadow-inner');
            btn.innerHTML = `
                <div class="absolute inset-0 bg-red-100/50"></div>
                <span class="relative z-10 text-red-500 font-mono text-xs mb-1 font-bold">#${student.classNum}</span>
                <span class="relative z-10 text-red-700 text-center w-full truncate px-1 font-bold">${student.name}</span>
                <div class="absolute top-1 right-1">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="text-red-500"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </div>
            `;
        } else if (student.status === 'absent') {
            btn.classList.add('bg-slate-100', 'border-slate-300', 'opacity-70');
            btn.innerHTML = `
                <span class="text-slate-400 font-mono text-xs mb-1">#${student.classNum}</span>
                <span class="text-slate-500 text-center w-full truncate px-1 line-through">${student.name}</span>
                <div class="absolute top-1 right-1">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-slate-400"><circle cx="12" cy="12" r="10"></circle><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line></svg>
                </div>
            `;
        }

        btn.onclick = () => window.toggleStatus(index);
        studentGrid.appendChild(btn);
    });

    window.updateOutput();
};

window.toggleStatus = (index) => {
    const currentStatus = students[index].status;
    if (currentStatus === 'present') students[index].status = 'missing';
    else if (currentStatus === 'missing') students[index].status = 'absent';
    else students[index].status = 'present';
    
    window.renderGrid();
};

window.updateOutput = () => {
    const hwName = assignmentInput.value.trim() || 'Homework';
    
    const missing = students.filter(s => s.status === 'missing');
    if (missing.length === 0) {
        outputMessage.innerHTML = `<span class="text-slate-400 italic">No missing students recorded yet.</span>`;
    } else {
        let msg = `[${hwName} - Missing List]\n\n`;
        missing.forEach(s => msg += `${s.classNum}. ${s.name}\n`);
        msg += `\nTotal Missing: ${missing.length}`;
        outputMessage.innerText = msg;
    }

    const absent = students.filter(s => s.status === 'absent');
    if (absent.length === 0) {
        outputAbsent.innerHTML = `<span class="text-slate-400 italic">No absent students recorded yet.</span>`;
    } else {
        let msg = `[${hwName} - Absent List]\n\n`;
        absent.forEach(s => msg += `${s.classNum}. ${s.name}\n`);
        msg += `\nTotal Absent: ${absent.length}`;
        outputAbsent.innerText = msg;
    }
};

window.copyMessage = (elementId) => {
    const el = document.getElementById(elementId);
    const text = el.innerText;
    if (text.includes('No missing students') || text.includes('No absent students')) return;

    navigator.clipboard.writeText(text).then(() => {
        const btnId = elementId === 'output-message' ? 'copy-btn-missing' : 'copy-btn-absent';
        const btn = document.getElementById(btnId);
        const originalHtml = btn.innerHTML;
        
        btn.classList.add('bg-green-50', 'text-green-700', 'border-green-200');
        btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg> Copied!`;
        
        setTimeout(() => {
            btn.classList.remove('bg-green-50', 'text-green-700', 'border-green-200');
            btn.innerHTML = originalHtml;
        }, 2000);
    });
};

// ==========================================
// Excel Import / Export (Current Roster)
// ==========================================

window.handleExcelUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
        const data = new Uint8Array(event.target.result);
        const workbook = XLSX.read(data, { type: 'array' });
        const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
        const jsonData = XLSX.utils.sheet_to_json(firstSheet, { header: 1 });

        let parsedText = '';
        jsonData.forEach(row => {
            if (row.length >= 2) {
                const no = row[0];
                const name = row[1];
                if (no && name && !isNaN(no)) {
                    parsedText += `${no} ${name}\n`;
                }
            }
        });

        if (parsedText) {
            classListInput.value = parsedText.trim();
            window.parseInput();
        } else {
            alert("Could not find valid 'Class No' and 'Name' columns in the Excel file. Please ensure column A is Number and column B is Name.");
        }
    };
    reader.readAsArrayBuffer(file);
    e.target.value = '';
};

window.exportToExcel = () => {
    if (students.length === 0) {
        alert("No student data to export.");
        return;
    }

    const data = students.map(s => ({
        "Class Number": s.classNum,
        "Student Name": s.name,
        "Status": s.status.charAt(0).toUpperCase() + s.status.slice(1)
    }));

    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Homework Status");

    const fileName = getFormattedFileName('xlsx');
    
    const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
    const blob = new Blob([wbout], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    
    saveFileWithDialog(blob, fileName, {
        description: 'Excel Workbook',
        accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] }
    });
};

// ==========================================
// Local File-Based Tracking (Database)
// ==========================================

window.renderLocalRecords = () => {
    const threshold = parseInt(document.getElementById('flag-threshold').value, 10);
    const tbody = document.getElementById('local-records-tbody');
    const emptyStateEl = document.getElementById('local-empty-state');
    
    const grouped = {};
    localRecords.forEach(r => {
        const key = `${r.classNum}_${r.studentName}`;
        if (!grouped[key]) {
            grouped[key] = { 
                classNum: parseInt(r.classNum, 10) || r.classNum, 
                name: r.studentName, 
                count: 0, 
                assignments: [] 
            };
        }
        grouped[key].count++;
        grouped[key].assignments.push(r.assignmentName);
    });

    const flagged = Object.values(grouped)
        .filter(s => s.count >= threshold)
        .sort((a, b) => {
            if (b.count !== a.count) return b.count - a.count;
            return a.classNum - b.classNum;
        });

    tbody.innerHTML = '';
    
    if (flagged.length === 0) {
        emptyStateEl.classList.remove('hidden');
        tbody.parentElement.classList.add('hidden');
    } else {
        emptyStateEl.classList.add('hidden');
        tbody.parentElement.classList.remove('hidden');
        
        flagged.forEach(s => {
            const tr = document.createElement('tr');
            tr.className = "hover:bg-slate-50 transition-colors";
            
            let badgeClass = "bg-slate-100 text-slate-800";
            if (s.count >= 10) badgeClass = "bg-red-100 text-red-800 ring-1 ring-red-200";
            else if (s.count >= 5) badgeClass = "bg-orange-100 text-orange-800 ring-1 ring-orange-200";
            else if (s.count >= 3) badgeClass = "bg-amber-100 text-amber-800 ring-1 ring-amber-200";

            tr.innerHTML = `
                <td class="px-6 py-4 font-mono text-center text-slate-500">${s.classNum}</td>
                <td class="px-6 py-4 font-semibold text-slate-900">${s.name}</td>
                <td class="px-6 py-4 text-center">
                    <span class="inline-flex items-center justify-center px-2.5 py-1 rounded-full text-xs font-bold ${badgeClass}">
                        ${s.count} Missed
                    </span>
                </td>
                <td class="px-6 py-4 text-xs text-slate-600 leading-relaxed">
                    ${s.assignments.join('<br><span class="text-slate-300">|</span> ')}
                </td>
            `;
            tbody.appendChild(tr);
        });
    }
};

window.addToTracker = () => {
    const missingStudents = students.filter(s => s.status === 'missing');
    if (missingStudents.length === 0) {
        alert("There are no 'Missing' students marked in the roster to add.");
        return;
    }
    
    const hwName = assignmentInput.value.trim() || 'Unnamed Assignment';
    const dateStr = new Date().toISOString();

    missingStudents.forEach(s => {
        localRecords.push({
            id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString() + Math.random(),
            classNum: s.classNum,
            studentName: s.name,
            assignmentName: hwName,
            date: dateStr,
            timestamp: Date.now()
        });
    });

    window.renderLocalRecords();
    
    const addBtn = document.getElementById('add-tracker-btn');
    const originalHtml = addBtn.innerHTML;
    
    addBtn.classList.replace('bg-indigo-600', 'bg-green-600');
    addBtn.classList.replace('hover:bg-indigo-700', 'hover:bg-green-700');
    addBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg> Added to Tracker!`;
    
    setTimeout(() => {
        addBtn.innerHTML = originalHtml;
        addBtn.classList.replace('bg-green-600', 'bg-indigo-600');
        addBtn.classList.replace('hover:bg-green-700', 'hover:bg-indigo-700');
    }, 3000);
};

window.downloadDatabase = () => {
    if (localRecords.length === 0) {
        alert("There are no records to backup.");
        return;
    }
    
    const fileName = getFormattedFileName('json', 'Backup');
    const jsonStr = JSON.stringify(localRecords, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    
    saveFileWithDialog(blob, fileName, {
        description: 'JSON Database',
        accept: { 'application/json': ['.json'] }
    });
};

window.loadDatabase = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const data = JSON.parse(e.target.result);
            if (Array.isArray(data)) {
                localRecords = data;
                window.renderLocalRecords();
                alert("Database backup loaded successfully.");
            } else {
                alert("Invalid backup file format.");
            }
        } catch (err) {
            alert("Error reading backup file.");
        }
        event.target.value = '';
    };
    reader.readAsText(file);
};

window.exportFlagsToExcel = () => {
    if (localRecords.length === 0) {
        alert("No records found in tracker to export.");
        return;
    }
    
    const threshold = parseInt(document.getElementById('flag-threshold').value, 10);
    
    const grouped = {};
    localRecords.forEach(r => {
        const key = `${r.classNum}_${r.studentName}`;
        if (!grouped[key]) {
            grouped[key] = { classNum: parseInt(r.classNum, 10) || r.classNum, name: r.studentName, count: 0, assignments: [] };
        }
        grouped[key].count++;
        grouped[key].assignments.push(r.assignmentName);
    });

    const flagged = Object.values(grouped)
        .filter(s => s.count >= threshold)
        .sort((a, b) => b.count - a.count);

    if (flagged.length === 0) {
        alert(`No students found with ${threshold}+ missed assignments to export.`);
        return;
    }

    const data = flagged.map(s => ({
        "Class Number": s.classNum,
        "Student Name": s.name,
        "Times Missed": s.count,
        "Assignments Missed": s.assignments.join(', ')
    }));

    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, `Flagged (${threshold}+)`);

    const fileName = getFormattedFileName('xlsx', 'Flagged');
    
    const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
    const blob = new Blob([wbout], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    
    saveFileWithDialog(blob, fileName, {
        description: 'Excel Workbook',
        accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] }
    });
};

// Initialize empty state
window.renderGrid();