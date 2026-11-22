import React, { useState, useEffect, useRef } from 'react';
import ROSLIB from 'roslib';

export default function App() {
  const [connected, setConnected] = useState(false);
  const [pose, setPose] = useState({ x: '0.00', y: '0.00', theta: '0.0' });
  const [navStatus, setNavStatus] = useState('IDLE');
  const [goal, setGoal] = useState({ x: 1.0, y: 0.0, yawDeg: '' });
  const [scanData, setScanData] = useState([]);
  const [missionState, setMissionState] = useState('SIN MISIÓN');
  const [missionProgress, setMissionProgress] = useState('0 / 0 puntos');
  const [missionBusy, setMissionBusy] = useState(false);
  
  const rosRef = useRef(null);
  const canvasRef = useRef(null);
  const poseRef = useRef({ x: 0, y: 0, yawRad: 0, frameId: '', receivedAt: 0 });

  // Paro lógico: solicita cancelar todos los objetivos NavigateToPose y publica Twist cero.
  // No sustituye un E-stop físico cableado ni una función de seguridad certificada.
  const forceStopRobot = () => {
    if (!rosRef.current) return;
    const stopService = new ROSLIB.Service({
      ros: rosRef.current,
      name: '/dif_bot/stop',
      serviceType: 'std_srvs/Trigger'
    });
    stopService.callService(new ROSLIB.ServiceRequest({}), (response) => {
      if (!response.success) setNavStatus(`PARO NO CONFIRMADO: ${response.message}`);
    }, (error) => {
      setNavStatus(`ERROR AL SOLICITAR PARO: ${error}`);
    });
  };

  useEffect(() => {
    const ros = new ROSLIB.Ros({
      url: `ws://${window.location.hostname}:9090`
    });

    ros.on('connection', () => setConnected(true));
    ros.on('error', () => setConnected(false));
    ros.on('close', () => setConnected(false));

    rosRef.current = ros;

    // Suscripción a Pose
    const poseSub = new ROSLIB.Topic({
      ros: ros,
      name: '/dif_bot/web/robot_pose',
      messageType: 'geometry_msgs/PoseStamped'
    });
    poseSub.subscribe((msg) => {
      const yawRad = Math.atan2(
        2 * (msg.pose.orientation.w * msg.pose.orientation.z + msg.pose.orientation.x * msg.pose.orientation.y),
        1 - 2 * (msg.pose.orientation.y ** 2 + msg.pose.orientation.z ** 2)
      );
      poseRef.current = {
        x: msg.pose.position.x,
        y: msg.pose.position.y,
        yawRad,
        frameId: String(msg.header.frame_id || '').replace('/', ''),
        receivedAt: Date.now()
      };
      setPose({
        x: msg.pose.position.x.toFixed(2),
        y: msg.pose.position.y.toFixed(2),
        theta: (yawRad * 180 / Math.PI).toFixed(1)
      });
    });

    // Suscripción a Estado Nav2 con Detención Automática
    const statusSub = new ROSLIB.Topic({
      ros: ros,
      name: '/dif_bot/web/nav_status',
      messageType: 'std_msgs/String'
    });
    statusSub.subscribe((msg) => {
      const status = msg.data;
      setNavStatus(status);
      

    });

    // Suscripción a LiDAR 2D
    const scanSub = new ROSLIB.Topic({
      ros: ros,
      name: '/dif_bot/web/scan',
      messageType: 'sensor_msgs/LaserScan'
    });
    scanSub.subscribe((msg) => setScanData(msg.ranges));

    const missionSub = new ROSLIB.Topic({
      ros, name: '/dif_bot/mission/progress', messageType: 'std_msgs/String'
    });
    missionSub.subscribe((msg) => {
      const fields = msg.data.split('|');
      setMissionState(fields[0] || msg.data);
      if (fields.length >= 3) setMissionProgress(`${fields[1]} / ${fields[2]} puntos`);
      if (['MISION_COMPLETADA', 'FALLIDA', 'ERROR'].includes(fields[0])) setMissionBusy(false);
    });

    // Eventos de teclado (W, A, S, D, Espacio, K)
    const handleKeyDown = (e) => {
      if (e.target.tagName === 'INPUT') return;
      if (e.key === ' ' || e.key.toLowerCase() === 'k') {
        forceStopRobot();
      } else if (e.key.toLowerCase() === 'w') {
        sendTwist(0.2, 0.0);
      } else if (e.key.toLowerCase() === 's') {
        sendTwist(-0.2, 0.0);
      } else if (e.key.toLowerCase() === 'a') {
        sendTwist(0.0, 0.5);
      } else if (e.key.toLowerCase() === 'd') {
        sendTwist(0.0, -0.5);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      poseSub.unsubscribe(); statusSub.unsubscribe(); scanSub.unsubscribe(); missionSub.unsubscribe();
      ros.close();
    };
  }, []);

  // Función para determinar el color según el estado semántico de Nav2
  const getStatusColor = (status) => {
    if (!status) return '#9ca3af';
    const s = status.toUpperCase();
    if (s.includes('SUCCEEDED') || s.includes('ÉXITO') || s.includes('EXITO')) return '#34d399'; // Verde
    if (s.includes('EN_RUTA') || s.includes('EN PROG') || s.includes('EXECUTING') || s.includes('ENVIANDO')) return '#38bdf8'; // Azul Neón
    if (s.includes('ABORT') || s.includes('ERROR') || s.includes('FALLO')) return '#f43f5e'; // Rojo
    return '#9ca3af'; // Gris IDLE neutro por defecto
  };

  // Renderizado del Canvas LiDAR 2D
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const scale = 40;

    ctx.fillStyle = '#030712';
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = '#1f2937';
    ctx.lineWidth = 1;
    for (let r = 40; r < width / 2; r += 40) {
      ctx.beginPath();
      ctx.arc(centerX, centerY, r, 0, 2 * Math.PI);
      ctx.stroke();
    }

    if (scanData.length > 0) {
      ctx.fillStyle = '#38bdf8';
      const angleStep = (2 * Math.PI) / scanData.length;
      scanData.forEach((range, i) => {
        if (range > 0.05 && range < 10.0) {
          const angle = i * angleStep;
          const px = centerX + range * scale * Math.cos(angle);
          const py = centerY - range * scale * Math.sin(angle);
          ctx.beginPath();
          ctx.arc(px, py, 1.8, 0, 2 * Math.PI);
          ctx.fill();
        }
      });
    }

    ctx.fillStyle = '#f43f5e';
    ctx.beginPath();
    ctx.arc(centerX, centerY, 7, 0, 2 * Math.PI);
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.stroke();

  }, [scanData]);

  const sendTwist = (linear, angular) => {
    if (!rosRef.current) return;
    const cmdVel = new ROSLIB.Topic({
      ros: rosRef.current,
      name: '/cmd_vel_web',
      messageType: 'geometry_msgs/Twist'
    });
    cmdVel.publish(new ROSLIB.Message({
      linear: { x: linear, y: 0.0, z: 0.0 },
      angular: { x: 0.0, y: 0.0, z: angular }
    }));
  };

  const startAutonomousMission = () => {
    if (!rosRef.current || !connected || missionBusy) return;
    const service = new ROSLIB.Service({
      ros: rosRef.current,
      name: '/start_autonomous_mission',
      serviceType: 'std_srvs/Trigger'
    });
    setMissionBusy(true);
    setMissionState('SOLICITANDO');
    service.callService(new ROSLIB.ServiceRequest({}), (response) => {
      setMissionState(response.success ? 'ACEPTADA' : `RECHAZADA: ${response.message}`);
      if (!response.success) setMissionBusy(false);
    }, (error) => {
      setMissionState(`ERROR DE SERVICIO: ${error}`);
      setMissionBusy(false);
    });
  };

  const sendGoal = () => {
    if (!rosRef.current || !connected) { setNavStatus('ERROR: rosbridge no está conectado.'); return; }
    const targetX = Number(goal.x);
    const targetY = Number(goal.y);
    if (!Number.isFinite(targetX) || !Number.isFinite(targetY)) { setNavStatus('ERROR: X e Y deben ser coordenadas numéricas válidas.'); return; }
    const currentPose = poseRef.current;
    const yawText = String(goal.yawDeg ?? '').trim();
    let targetYaw;
    if (yawText === '') {
      const poseIsFresh = currentPose.receivedAt > 0 && Date.now() - currentPose.receivedAt <= 2000;
      if (!poseIsFresh || currentPose.frameId !== 'map') {
        setNavStatus('ERROR: No hay una pose reciente del robot en frame map para conservar su orientación.');
        return;
      }
      targetYaw = currentPose.yawRad;
    } else {
      const yawDegrees = Number(yawText);
      if (!Number.isFinite(yawDegrees)) { setNavStatus('ERROR: El yaw final debe ser un ángulo numérico en grados.'); return; }
      targetYaw = yawDegrees * Math.PI / 180.0;
    }
    targetYaw = Math.atan2(Math.sin(targetYaw), Math.cos(targetYaw));
    const halfYaw = targetYaw / 2.0;
    const targetYawDegrees = targetYaw * 180.0 / Math.PI;
    setNavStatus('EN_RUTA: Enviando X=' + targetX.toFixed(2) + ', Y=' + targetY.toFixed(2) + ', yaw=' + targetYawDegrees.toFixed(1) + '°...');
    const goalMsg = new ROSLIB.Message({
      header: { frame_id: 'map' },
      pose: {
        position: { x: targetX, y: targetY, z: 0.0 },
        orientation: { x: 0.0, y: 0.0, z: Math.sin(halfYaw), w: Math.cos(halfYaw) }
      }
    });
    const goalTopic = new ROSLIB.Topic({
      ros: rosRef.current, name: '/dif_bot/web/goal_pose',
      messageType: 'geometry_msgs/PoseStamped'
    });
    goalTopic.publish(goalMsg);
  };

  return (
    <div style={{ backgroundColor: '#030712', color: '#f9fafb', minHeight: '100vh', padding: '1.5rem', fontFamily: 'system-ui, sans-serif' }}>
      
      {/* FRANJA SUPERIOR REESTRUCTURADA */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', backgroundColor: '#111827', padding: '1rem 1.5rem', borderRadius: '0.75rem', border: '1px solid #1f2937' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ width: '12px', height: '12px', backgroundColor: '#38bdf8', borderRadius: '3px' }} />
          <h1 style={{ fontSize: '1.35rem', fontWeight: '800', margin: 0, color: '#f9fafb', letterSpacing: '-0.025em' }}>
            dif_bot OS <span style={{ fontSize: '0.85rem', color: '#9ca3af', fontWeight: '400', marginLeft: '0.5rem' }}>— Central de Control & Navegación Autónoma</span>
          </h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', backgroundColor: connected ? '#064e3b' : '#7f1d1d', padding: '0.35rem 0.75rem', borderRadius: '0.5rem', border: `1px solid ${connected ? '#059669' : '#dc2626'}` }}>
          <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: connected ? '#34d399' : '#f87171' }} />
          <span style={{ fontSize: '0.8rem', fontWeight: '700', color: connected ? '#a7f3d0' : '#fca5a5' }}>
            {connected ? 'WS CONECTADO (9090)' : 'DESCONECTADO'}
          </span>
        </div>
      </header>

      {/* BENTO GRID OSCURO */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '1.25rem' }}>
        
        {/* HERO CELL: LIDAR 2D (8 COLUMNAS) */}
        <div style={{ gridColumn: 'span 8', backgroundColor: '#111827', borderRadius: '0.75rem', padding: '1.25rem', border: '1px solid #1f2937', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <span style={{ fontWeight: '700', color: '#f3f4f6', fontSize: '0.95rem' }}>Visualización LiDAR 2D en Tiempo Real</span>
            <span style={{ fontSize: '0.75rem', color: '#38bdf8', backgroundColor: '#0c4a6e', padding: '0.25rem 0.6rem', borderRadius: '0.375rem', fontWeight: '600' }}>Sensor Láser Activo</span>
          </div>
          <canvas ref={canvasRef} width={700} height={460} style={{ width: '100%', height: 'auto', borderRadius: '0.5rem', border: '1px solid #1f2937' }} />
        </div>

        {/* CONTROLES LATERALES (4 COLUMNAS) */}
        <div style={{ gridColumn: 'span 4', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          
          <div style={{ backgroundColor: '#111827', borderRadius: '0.75rem', padding: '1.25rem', border: '1px solid #1f2937' }}>
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.9rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Telemetría del Chasis</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div style={{ backgroundColor: '#1f2937', padding: '0.75rem', borderRadius: '0.5rem' }}>
                <span style={{ fontSize: '0.7rem', color: '#9ca3af' }}>Posición X</span>
                <p style={{ margin: 0, fontSize: '1.3rem', fontWeight: '800', color: '#38bdf8' }}>{pose.x} <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>m</span></p>
              </div>
              <div style={{ backgroundColor: '#1f2937', padding: '0.75rem', borderRadius: '0.5rem' }}>
                <span style={{ fontSize: '0.7rem', color: '#9ca3af' }}>Posición Y</span>
                <p style={{ margin: 0, fontSize: '1.3rem', fontWeight: '800', color: '#38bdf8' }}>{pose.y} <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>m</span></p>
              </div>
            </div>
            <div style={{ marginTop: '0.75rem', backgroundColor: '#1f2937', padding: '0.75rem', borderRadius: '0.5rem' }}>
              <span style={{ fontSize: '0.7rem', color: '#9ca3af' }}>Estado Nav2</span>
              <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.95rem', fontWeight: '700', color: getStatusColor(navStatus), transition: 'color 0.3s ease' }}>{navStatus}</p>
            </div>
          </div>

          <div style={{ backgroundColor: '#111827', borderRadius: '0.75rem', padding: '1.25rem', border: '1px solid #1f2937' }}>
            <h3 style={{ margin: '0 0 0.8rem 0', fontSize: '0.9rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Misión secuencial</h3>
            <div style={{ color: '#38bdf8', fontWeight: 800, marginBottom: '0.3rem' }}>{missionState}</div>
            <div style={{ color: '#9ca3af', fontSize: '0.85rem', marginBottom: '0.8rem' }}>{missionProgress}</div>
            <button onClick={startAutonomousMission} disabled={!connected || missionBusy}
              style={{ width: '100%', background: missionBusy ? '#374151' : '#0369a1', color: '#fff', border: 0, padding: '0.7rem', borderRadius: '0.5rem', fontWeight: 700, cursor: missionBusy ? 'not-allowed' : 'pointer', opacity: connected ? 1 : 0.5 }}>
              {missionBusy ? 'MISIÓN EN EJECUCIÓN' : 'INICIAR MISIÓN AUTÓNOMA'}
            </button>
          </div>

          <div style={{ backgroundColor: '#111827', borderRadius: '0.75rem', padding: '1.25rem', border: '1px solid #1f2937' }}>
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.9rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Misiones de Navegación</h3>
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <input type="number" step="0.1" value={goal.x}
                onChange={(e) => setGoal({ ...goal, x: e.target.value })} placeholder="Meta X (m)"
                style={{ width: '50%', backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff', padding: '0.6rem', borderRadius: '0.5rem', outline: 'none' }} />
              <input type="number" step="0.1" value={goal.y}
                onChange={(e) => setGoal({ ...goal, y: e.target.value })} placeholder="Meta Y (m)"
                style={{ width: '50%', backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff', padding: '0.6rem', borderRadius: '0.5rem', outline: 'none' }} />
            </div>
            <div style={{ marginBottom: '0.75rem' }}>
              <input type="number" step="1" value={goal.yawDeg}
                onChange={(e) => setGoal({ ...goal, yawDeg: e.target.value })}
                placeholder="Yaw final (grados; vacío = conservar orientación)"
                style={{ width: '100%', boxSizing: 'border-box', backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff', padding: '0.6rem', borderRadius: '0.5rem', outline: 'none' }} />
              <span style={{ display: 'block', marginTop: '0.35rem', color: '#9ca3af', fontSize: '0.7rem' }}>
                Sin yaw indicado, el robot conserva su orientación al enviar la meta. Ejemplo: 90° apunta hacia +Y.
              </span>
            </div>
            <button 
              onClick={sendGoal} 
              style={{ width: '100%', backgroundColor: '#0284c7', color: '#fff', border: 'none', padding: '0.75rem', borderRadius: '0.5rem', fontWeight: '700', cursor: 'pointer' }}
            >
              Enviar Objetivo
            </button>
          </div>

        </div>

        {/* BANDA INFERIOR: TELEOPERACIÓN + PARO LÓGICO (12 COLUMNAS) */}
        <div style={{ gridColumn: 'span 12', backgroundColor: '#111827', borderRadius: '0.75rem', padding: '1.25rem', border: '1px solid #1f2937', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#f3f4f6', fontWeight: '700' }}>Teleoperación Manual & Paro por Comando</h3>
            <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Teclas [W, A, S, D] para mover | [Espacio / K] cancela Nav2 y solicita velocidad cero</span>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={() => sendTwist(0.2, 0.0)} style={{ backgroundColor: '#1f2937', color: '#38bdf8', border: '1px solid #374151', padding: '0.6rem 1.25rem', borderRadius: '0.5rem', fontWeight: '700', cursor: 'pointer' }}>W</button>
            <button onClick={() => sendTwist(0.0, 0.5)} style={{ backgroundColor: '#1f2937', color: '#38bdf8', border: '1px solid #374151', padding: '0.6rem 1.25rem', borderRadius: '0.5rem', fontWeight: '700', cursor: 'pointer' }}>A</button>
            <button onClick={forceStopRobot} style={{ backgroundColor: '#dc2626', color: '#fff', border: 'none', padding: '0.6rem 1.5rem', borderRadius: '0.5rem', fontWeight: '800', cursor: 'pointer', letterSpacing: '0.05em' }}>STOP POR COMANDO (Espacio / K)</button>
            <button onClick={() => sendTwist(0.0, -0.5)} style={{ backgroundColor: '#1f2937', color: '#38bdf8', border: '1px solid #374151', padding: '0.6rem 1.25rem', borderRadius: '0.5rem', fontWeight: '700', cursor: 'pointer' }}>D</button>
            <button onClick={() => sendTwist(-0.2, 0.0)} style={{ backgroundColor: '#1f2937', color: '#38bdf8', border: '1px solid #374151', padding: '0.6rem 1.25rem', borderRadius: '0.5rem', fontWeight: '700', cursor: 'pointer' }}>S</button>
          </div>
        </div>

      </div>
    </div>
  );
}
