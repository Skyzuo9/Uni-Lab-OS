import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import URDFLoader from 'urdf-loader';

let scene, camera, renderer, controls, robot;

export function createScene(container) {
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x263238);

    camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.01, 100);
    camera.position.set(2, 2, 3);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0.5, 0);
    controls.update();

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(5, 10, 7);
    scene.add(dirLight);

    const grid = new THREE.GridHelper(10, 20, 0x444444, 0x333333);
    scene.add(grid);

    scene.add(new THREE.AxesHelper(1));

    window.addEventListener('resize', () => {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });

    return scene;
}

export function loadURDF(urdfUrl, meshBaseUrl = '') {
    return new Promise((resolve, reject) => {
        fetch(urdfUrl)
            .then(res => res.text())
            .then(urdfContent => {
                const loader = new URDFLoader();
                loader.parseVisual = true;
                loader.packages = '';
                loader.workingPath = meshBaseUrl;

                const result = loader.parse(urdfContent);
                robot = result;
                scene.add(robot);
                resolve(robot);
            })
            .catch(reject);
    });
}

export function updateJointState(jointState) {
    if (!robot || !robot.joints) return;

    const { name, position } = jointState;
    for (let i = 0; i < name.length; i++) {
        const joint = robot.joints[name[i]];
        if (joint) {
            joint.setJointValue(position[i]);
        }
    }
}

export function getDeviceMeshNames() {
    const names = [];
    if (robot) {
        robot.traverse(child => {
            if (child.name) names.push(child.name);
        });
    }
    return names;
}

export function loadURDFText(urdfContent, meshBaseUrl = '') {
    if (robot) { scene.remove(robot); robot = null; }
    const loader = new URDFLoader();
    loader.parseVisual = true;
    loader.packages = '';
    loader.workingPath = meshBaseUrl;
    robot = loader.parse(urdfContent);
    scene.add(robot);
    return robot;
}

export function clearRobot() {
    if (robot) { scene.remove(robot); robot = null; }
}

export function getRobot() { return robot; }
export function getScene() { return scene; }

export function animate() {
    requestAnimationFrame(animate);
    controls?.update();
    renderer?.render(scene, camera);
}