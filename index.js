require('dotenv').config();
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const { GoogleSpreadsheet } = require('google-spreadsheet');
const { JWT } = require('google-auth-library');
const cron = require('node-cron');

// Initialize the WhatsApp Client
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu'
        ]
    }
});

const readline = require('readline');

client.once('qr', async (qr) => {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    console.log('\n======================================================');
    rl.question('📱 Enter your WhatsApp phone number (with country code, e.g., 919876543210): ', async (phoneNumber) => {
        try {
            console.log('\n⏳ Requesting pairing code from WhatsApp...');
            let code = await client.requestPairingCode(phoneNumber.trim());
            console.log('\n======================================================');
            console.log(`🔑 YOUR PAIRING CODE IS: ${code}`);
            console.log('Open WhatsApp on your phone:');
            console.log('1. Go to Settings > Linked Devices > Link a Device');
            console.log('2. Tap "Link with phone number instead" at the bottom');
            console.log('3. Enter the code above.');
            console.log('======================================================\n');
        } catch (err) {
            console.error('❌ Error generating pairing code:', err.message);
            console.log('Make sure you entered the phone number with country code (no + sign).');
        }
        rl.close();
    });
});

client.on('authenticated', () => {
    console.log('\n🔐 Authentication successful! Saving session...');
});

client.on('auth_failure', (msg) => {
    console.error('\n❌ Authentication failed:', msg);
});

client.on('loading_screen', (percent, message) => {
    console.log(`🔄 Loading... ${percent}% | ${message}`);
});

client.on('ready', async () => {
    console.log('✅ Client is ready! Connected to WhatsApp.\n');

    // Run immediately on startup
    await checkAndSendMessages();

    // Then schedule to run every day at 8:00 AM
    cron.schedule('0 8 * * *', async () => {
        console.log('\n⏰ Scheduled 8:00 AM run triggered!');
        await checkAndSendMessages();
    });

    console.log('\n🕐 Bot is now running 24/7. Next check at 8:00 AM tomorrow.');
    console.log('   Keep this terminal open (or deploy to cloud). Press Ctrl+C to stop.\n');
});

// Helper: Parse DD-MM-YYYY date string into a Date object
function parseDate(dateStr) {
    if (!dateStr || dateStr.trim() === '') return null;
    const parts = dateStr.trim().split('-');
    if (parts.length !== 3) return null;
    const day = parseInt(parts[0], 10);
    const month = parseInt(parts[1], 10);
    const year = parseInt(parts[2], 10);
    if (isNaN(day) || isNaN(month) || isNaN(year)) return null;
    return { day, month, year };
}

// Helper: Format phone number (auto-add 91 if needed)
function formatPhone(phone) {
    if (!phone) return null;
    let cleaned = phone.toString().replace(/\D/g, ''); // Remove non-digits
    if (cleaned.length === 10) {
        cleaned = '91' + cleaned; // Auto-add India country code
    }
    return cleaned;
}

async function checkAndSendMessages() {
    console.log(`[${new Date().toLocaleString()}] Connecting to Google Sheets...`);

    try {
        const serviceAccountAuth = new JWT({
            email: process.env.GOOGLE_SERVICE_ACCOUNT_EMAIL,
            key: process.env.GOOGLE_PRIVATE_KEY.replace(/\\n/g, '\n'),
            scopes: ['https://www.googleapis.com/auth/spreadsheets'],
        });

        const doc = new GoogleSpreadsheet(process.env.GOOGLE_SHEET_ID, serviceAccountAuth);

        await doc.loadInfo();
        console.log(`📄 Spreadsheet: "${doc.title}"`);

        // Find the correct tab
        let sheet = null;
        for (let i = 0; i < doc.sheetCount; i++) {
            const s = doc.sheetsByIndex[i];
            try {
                await s.loadHeaderRow();
                const headers = s.headerValues || [];
                if (headers.includes('Name') || headers.includes('Phone')) {
                    sheet = s;
                    console.log(`📋 Using tab: "${s.title}"`);
                    break;
                }
            } catch (e) { /* skip tabs without headers */ }
        }

        if (!sheet) {
            sheet = doc.sheetsByIndex[0];
            await sheet.loadHeaderRow();
        }

        const rows = await sheet.getRows();
        console.log(`📊 Found ${rows.length} customer rows.`);

        const today = new Date();
        const currentDay = today.getDate();
        const currentMonth = today.getMonth() + 1;
        const currentYear = today.getFullYear();
        console.log(`📅 Today: ${currentDay}-${currentMonth}-${currentYear}\n`);

        // Track phones that already got birthday messages (avoid duplicates)
        const birthdaySent = new Set();

        for (const row of rows) {
            const name = row.get('Name');
            const rawPhone = row.get('Phone');
            const dobString = row.get('DOB');
            const refillDateString = row.get('NextRefillDate');
            const medicineString = row.get('MedicineName');

            const phone = formatPhone(rawPhone);
            if (!phone) { continue; }

            const chatId = `${phone}@c.us`;
            console.log(`👤 ${name} | Phone: ${phone} | DOB: "${dobString}" | Refill: "${refillDateString}" | Medicines: "${medicineString}"`);

            // 1. Birthday Check (only month + day, ignore year)
            if (dobString && !birthdaySent.has(phone)) {
                const dob = parseDate(dobString);
                if (dob && dob.month === currentMonth && dob.day === currentDay) {
                    await sendBirthdayMessage(name, chatId);
                    birthdaySent.add(phone);
                    await new Promise(resolve => setTimeout(resolve, 3000));
                }
            }

            // 2. Medicine Refill Check (exact date including year)
            if (refillDateString && medicineString) {
                const refill = parseDate(refillDateString);
                if (refill && refill.year === currentYear && refill.month === currentMonth && refill.day === currentDay) {
                    // Split comma-separated medicines into a clean list
                    const medicines = medicineString.split(',').map(m => m.trim()).filter(m => m);
                    await sendReminderMessage(name, chatId, medicines);
                    await new Promise(resolve => setTimeout(resolve, 3000));
                }
            }
        }

        console.log(`\n[${new Date().toLocaleString()}] ✅ Check complete!\n`);
    } catch (error) {
        console.error("❌ Error:", error.message);
    }
}

async function sendBirthdayMessage(name, chatId) {
    const message = `Dear ${name},\n\n*Warmest congratulations on your birthday from all of us at Mukesh Medical Hall!* 🎂\n\nTo make your day special, we are offering an exclusive *20% discount on your next purchase*.\n\nKindly present this message at the counter to redeem your discount. Valid for 2 days.\n\nStay healthy!\n*— Mukesh Medical Hall Team*`;
    try {
        await client.sendMessage(chatId, message);
        console.log(`   ✅ Birthday message sent to ${name}`);
    } catch (error) {
        console.error(`   ❌ Failed to send birthday message to ${name}:`, error.message);
    }
}

async function sendReminderMessage(name, chatId, medicines) {
    // Build a nicely formatted medicine list
    let medicineList;
    if (medicines.length === 1) {
        medicineList = `*${medicines[0]}*`;
    } else {
        medicineList = medicines.map((m, i) => `  ${i + 1}. *${m}*`).join('\n');
        medicineList = `\n${medicineList}`;
    }

    const message = `Hello ${name},\n\nThis is a friendly reminder from *Mukesh Medical Hall*. It looks like it's time to refill your prescription for:${medicines.length > 1 ? '\n' : ' '}${medicineList}\n\nReply 'YES' to prepare your order, or visit us at the shop.\n\nTake care!\n*— Mukesh Medical Hall Team*`;
    try {
        await client.sendMessage(chatId, message);
        console.log(`   ✅ Reminder sent to ${name} for ${medicines.length} medicine(s)`);
    } catch (error) {
        console.error(`   ❌ Failed to send reminder to ${name}:`, error.message);
    }
}

console.log("🚀 Starting Mukesh Medical Hall WhatsApp Bot...");
client.initialize();
