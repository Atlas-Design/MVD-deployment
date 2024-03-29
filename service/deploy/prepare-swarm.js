#!/usr/bin/env node
const childProcess = require('node:child_process');
const path = require('node:path');

/**
 * @typedef {{ username: string, public_ip: string, swarm_node_type: string, swarm_labels: string[] }} SwarmNodeDefinition
 */

/**
 * @typedef {{ manager: string, worker: string }} SwarmJoinArgs
 */

/**
 * @typedef {{ nodes: { value: SwarmNodeDefinition[] } }} SwarmConfigType
 */

/**
 * @param command {string}
 * @param options {{ strict?: boolean }}
 * @return {Promise<{ exitCode: number, output: string }>}
 */
async function runCommand(command, options = {}) {
    const { strict = true } = options;

    return new Promise((resolve, reject) => {
        console.debug("Command:", command);
        const process = childProcess.spawn('bash', ['-c', command], { stdio: 'pipe' });

        let outBuffer = "";
        process.stdout.on('data', chunk => {
            outBuffer += chunk;
        });

        let errBuffer = "";
        process.stderr.on('data', chunk => {
            errBuffer += chunk;
        });

        process.on('exit', code => {
            // console.debug("Out:", outBuffer);
            // console.debug("Err:", errBuffer);
            // console.debug("Exit Code:", code);

            if (strict && code !== 0) {
                reject(new Error(`Non-zero (${code}) exit code for "${command}". \n Out: ${outBuffer}\n Err: ${errBuffer}`))
            } else {
                resolve({ exitCode: code, output: outBuffer })
            }
        });
    });
}

/**
 * @param nodes {SwarmNodeDefinition[]}
 * @return {SwarmNodeDefinition}
 */
function findMainManagerNode(nodes) {
    return nodes.find(node => node.swarm_labels.find(label => label === "manager.main=true"));
}

/**
 * @param node {SwarmNodeDefinition}
 * @return {Promise<{ joinArgs: SwarmJoinArgs, nodeId: string }>}
 */
async function prepareMainManager(node) {
    const sshHost = `${node.username}@${node.public_ip}`;
    const dockerCommand = `docker -H ssh://${sshHost}`

    const { nodeId } = await prepareNode(node, undefined, true);

    const managerJoinArgs = await runCommand(`${dockerCommand} swarm join-token manager`)
        .then(({ output }) => output.match(/--token .*/)[0]);
    const workerJoinArgs = await runCommand(`${dockerCommand} swarm join-token worker`)
        .then(({ output }) => output.match(/--token .*/)[0]);

    console.debug("Manager Join Args:", managerJoinArgs);
    console.debug("Worker Join Args:", workerJoinArgs);
    console.debug("NodeId:", nodeId);

    return {
        joinArgs: {
            manager: managerJoinArgs,
            worker: workerJoinArgs
        },
        nodeId: nodeId
    }
}

/**
 * @param node {SwarmNodeDefinition}
 * @param joinArgs {SwarmJoinArgs | undefined}
 * @param isMainNode {boolean}
 *
 * @return {Promise<{ nodeId: string }>}
 */
async function prepareNode(node, joinArgs = undefined, isMainNode = false) {
    const { exitCode } = await runCommand(`ssh-keygen -F "${node.public_ip}" 1>&2 >/dev/null`, { strict: false });
    if (exitCode !== 0) {
        await runCommand(`ssh-keyscan "${node.public_ip}" >> ~/.ssh/known_hosts`);
    }

    const sshHost = `${node.username}@${node.public_ip}`;

    // const daemonConfig = JSON.stringify({ "metrics-addr": "0.0.0.0:9323" }, null, 2);
    // await runCommand(`echo '${daemonConfig}' | ssh "${sshHost}" -T "sudo tee /etc/docker/daemon.json"`);

    const dockerCommand = `docker -H ssh://${sshHost}`

    const swarmStatus = await runCommand(`${dockerCommand} info`)
        .then(({ output }) => output.match(/Swarm: (?<status>\w+)/)?.groups?.status);

    console.debug("Swarm Node Type:", node.swarm_node_type);
    console.debug(`Swarm Status: "${swarmStatus}"`);

    if (!swarmStatus) {
        throw new Error("Could not check swarm status");
    }

    if (node.swarm_node_type === "manager") {
        if (swarmStatus === "inactive" && isMainNode) {
            await runCommand(`${dockerCommand} swarm init`);
        } else if (swarmStatus === "inactive") {
            await runCommand(`${dockerCommand} swarm join ${joinArgs.manager}`);
        }
    } else if (node.swarm_node_type === "worker") {
        if (swarmStatus === "inactive") {
            await runCommand(`${dockerCommand} swarm join ${joinArgs.worker}`);
        }
    }

    const nodeId = await runCommand(`${dockerCommand} info`)
        .then(({ output }) => output.match(/NodeID: (?<nodeId>\w+)/)?.groups?.nodeId);
    console.debug("NodeId:", nodeId);

    return { nodeId };
}

/**
 * @param managerNode {SwarmNodeDefinition}
 * @param node {SwarmNodeDefinition}
 * @param nodeId {string}
 */
async function setLabels(managerNode, node, nodeId) {
    const sshHost = `${managerNode.username}@${managerNode.public_ip}`;
    const dockerCommand = `docker -H ssh://${sshHost}`;

    // await runCommand(`${dockerCommand} node ls`);

    await runCommand(`${dockerCommand} node update ${node.swarm_labels.map(label => `--label-add ${label}`).join(" ")} ${nodeId}`);
}

async function main() {
    /**
     * @type {SwarmConfigType}
     */
    const swarmConfig = require(path.join(__dirname, "swarm-config.json"));
    console.log(swarmConfig, swarmConfig.nodes.value);

    const mainManagerNode = findMainManagerNode(swarmConfig.nodes.value);
    const { joinArgs, nodeId: mainManagerNodeId } = await prepareMainManager(mainManagerNode);

    /**
     * @type {Record<string, string>}
     */
    const nodeIds = {
        [mainManagerNode.public_ip]: mainManagerNodeId
    };

    for (const node of swarmConfig.nodes.value) {
        // Skip main manager node since it's already configured
        if (node.public_ip === mainManagerNode.public_ip) continue;

        const { nodeId } = await prepareNode(node, joinArgs);
        nodeIds[node.public_ip] = nodeId;
    }

    for (const node of swarmConfig.nodes.value) {
        await setLabels(mainManagerNode, node, nodeIds[node.public_ip]);
    }
}

main();