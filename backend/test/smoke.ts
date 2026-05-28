import request from 'supertest';
import { createApp } from '../src/app.js';

async function run() {
    const app = createApp();

    console.log('Checking /api/health...');
    const health = await request(app).get('/api/health').expect(200);
    if (!health.body || health.body.status !== 'healthy') {
        console.error('Health check failed', health.body);
        process.exit(1);
    }

    console.log('Creating demo user...');
    const create = await request(app)
        .post('/api/users')
        .send({ email: 'smoke@test.local', name: 'Smoke Tester' })
        .expect(201);

    const userId = create.body?.id;
    if (!userId) {
        console.error('User creation failed', create.body);
        process.exit(1);
    }

    console.log('Requesting recommendations...');
    const rec = await request(app).get(`/api/recommendations/${userId}`).expect(200);
    if (!rec.body || !Array.isArray(rec.body.recommendations)) {
        console.error('Recommendations endpoint failed', rec.body);
        process.exit(1);
    }

    console.log('Smoke test passed');
    process.exit(0);
}

run().catch((err) => {
    console.error(err);
    process.exit(1);
});
