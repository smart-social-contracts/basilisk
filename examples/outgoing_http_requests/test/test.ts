import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/outgoing_http_requests';

const outgoingHttpRequestsCanister = createActor(
    getCanisterId('outgoing_http_requests'),
    {
        agentOptions: {
            host: 'http://127.0.0.1:8000'
        }
    }
);

runTests(getTests(outgoingHttpRequestsCanister));
