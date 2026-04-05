import { Test } from '../../_test_lib';

export function getTests(arCanister: any): Test[] {
    return [
        {
            name: 'create_user',
            test: async () => {
                const result = await arCanister.create_user('testuser');
                return { Ok: result.username === 'testuser' && result.recording_ids.length === 0 };
            }
        },
        {
            name: 'read_users',
            test: async () => {
                const result = await arCanister.read_users();
                return { Ok: result.length >= 1 };
            }
        },
        {
            name: 'create_recording',
            test: async () => {
                const users = await arCanister.read_users();
                const userId = users[0].id;
                const audio = new Uint8Array([1, 2, 3, 4]);
                const result = await arCanister.create_recording(audio, 'test recording', userId);
                return { Ok: 'Ok' in result && result.Ok.name === 'test recording' };
            }
        },
        {
            name: 'read_recordings',
            test: async () => {
                const result = await arCanister.read_recordings();
                return { Ok: result.length >= 1 };
            }
        },
        {
            name: 'delete_recording',
            test: async () => {
                const recordings = await arCanister.read_recordings();
                const result = await arCanister.delete_recording(recordings[0].id);
                return { Ok: 'Ok' in result };
            }
        },
        {
            name: 'delete_user',
            test: async () => {
                const users = await arCanister.read_users();
                const result = await arCanister.delete_user(users[0].id);
                return { Ok: 'Ok' in result };
            }
        }
    ];
}
