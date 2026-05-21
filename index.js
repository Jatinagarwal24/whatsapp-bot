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
        dumpio: true, // This will print everything the hidden browser is doing
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu',
            '--log-level=3'
        ]
    }
});

client.on('disconnected', (reason) => {
    console.error('\n⚠️ Client was logged out or disconnected. Reason:', reason);
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

client.once('ready', async () => {
    console.log('✅ Client is ready! Connected to WhatsApp.\n');

    // Run immediately on startup (safe — sent flags prevent duplicates)
    await checkAndSendMessages();

    // Schedule main daily run at 8:00 AM
    cron.schedule('0 8 * * *', async () => {
        console.log('\n⏰ Scheduled 8:00 AM run triggered!');
        await checkAndSendMessages();
    });

    // Check every 30 minutes for newly added entries
    cron.schedule('*/30 * * * *', async () => {
        console.log('\n🔍 Checking for new entries...');
        await checkAndSendMessages();
    });

    console.log('\n🕐 Bot is now running 24/7.');
    console.log('   📋 Main check: Daily at 8:00 AM');
    console.log('   🔍 New entry check: Every 30 minutes');
    console.log('   Press Ctrl+C to stop.\n');
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

        // Ensure tracking columns exist in the sheet
        const headers = sheet.headerValues || [];
        if (!headers.includes('BirthdaySentOn') || !headers.includes('RefillSentOn')) {
            const newHeaders = [...headers];
            if (!headers.includes('BirthdaySentOn')) newHeaders.push('BirthdaySentOn');
            if (!headers.includes('RefillSentOn')) newHeaders.push('RefillSentOn');
            await sheet.setHeaderRow(newHeaders);
            console.log('📌 Added tracking columns: BirthdaySentOn, RefillSentOn');
        }

        const rows = await sheet.getRows();
        console.log(`📊 Found ${rows.length} customer rows.`);

        const today = new Date();
        const currentDay = today.getDate();
        const currentMonth = today.getMonth() + 1;
        const currentYear = today.getFullYear();
        const todayStr = `${String(currentDay).padStart(2, '0')}-${String(currentMonth).padStart(2, '0')}-${currentYear}`;
        console.log(`📅 Today: ${todayStr}\n`);

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

            const birthdaySentOn = (row.get('BirthdaySentOn') || '').trim();
            const refillSentOn = (row.get('RefillSentOn') || '').trim();

            // 1. Birthday Check (only month + day, ignore year)
            if (dobString && !birthdaySent.has(phone)) {
                const dob = parseDate(dobString);
                if (dob && dob.month === currentMonth && dob.day === currentDay) {
                    if (birthdaySentOn === todayStr) {
                        console.log(`   ⏭️ Birthday message already sent today, skipping.`);
                    } else {
                        await sendBirthdayMessage(name, chatId);
                        birthdaySent.add(phone);
                        row.set('BirthdaySentOn', todayStr);
                        await row.save();
                        console.log(`   📝 Marked birthday as sent for today.`);
                        await new Promise(resolve => setTimeout(resolve, 3000));
                    }
                }
            }

            // 2. Medicine Refill Check (exact date including year)
            if (refillDateString && medicineString) {
                const refill = parseDate(refillDateString);
                if (refill && refill.year === currentYear && refill.month === currentMonth && refill.day === currentDay) {
                    if (refillSentOn === todayStr) {
                        console.log(`   ⏭️ Refill reminder already sent today, skipping.`);
                    } else {
                        const medicines = medicineString.split(',').map(m => m.trim()).filter(m => m);
                        await sendReminderMessage(name, chatId, medicines);
                        row.set('RefillSentOn', todayStr);
                        await row.save();
                        console.log(`   📝 Marked refill as sent for today.`);
                        await new Promise(resolve => setTimeout(resolve, 3000));
                    }
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
client.initialize().then(() => {
    // Start a 45 second timer. If it doesn't say ready by then, take a screenshot!
    setTimeout(async () => {
        try {
            if (client.pupPage) {
                console.log('\n📸 [DEBUG] Taking a screenshot of the hidden browser to see what it is stuck on...');
                await client.pupPage.screenshot({ path: 'debug.png' });
                console.log('📸 [DEBUG] Screenshot saved as "debug.png" on the server!');
            }
        } catch (e) {
            console.error('Screenshot failed:', e);
        }
    }, 45000);
});
