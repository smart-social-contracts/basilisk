import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/audio_recorder';

const audioRecorderCanister = createActor(getCanisterId('audio_recorder'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(audioRecorderCanister));
