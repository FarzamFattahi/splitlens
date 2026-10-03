import type { InputImage, Split } from './types';

/** Original procedural artwork. Each demo file goes through the same audit as uploads. */
export async function createDemo(): Promise<InputImage[]> {
  const inputs: InputImage[] = [];
  const classes = ['ceramic', 'bottles', 'copper'];
  const create = async (
    label: string,
    variant: number,
    path: string,
    mode = 'normal',
    size = 512,
  ) => {
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = Math.round(size * 0.75);
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Your browser does not support the demo canvas.');
    ctx.scale(size / 512, size / 512);
    const palette = ['#e9e4da', '#e1e8e7', '#ebe1d4', '#dedfe6', '#d9e2e3', '#f0e6de', '#d6ded2'];
    ctx.fillStyle = palette[variant % palette.length];
    ctx.fillRect(0, 0, 512, 384);
    const backdrop = ctx.createLinearGradient(0, 0, 512, 384);
    backdrop.addColorStop(0, 'rgba(255,255,255,.42)');
    backdrop.addColorStop(1, 'rgba(39,52,52,.08)');
    ctx.fillStyle = backdrop;
    ctx.fillRect(0, 0, 512, 384);
    ctx.strokeStyle = 'rgba(35,49,46,.15)';
    ctx.lineWidth = 1;
    for (let y = 64; y < 384; y += 64) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(512, y);
      ctx.stroke();
    }
    const x = 230 + Math.sin(variant * 2.4) * 50;
    const y = 215 + Math.cos(variant * 1.6) * 18;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate((variant - 3) * 0.105);
    ctx.fillStyle = 'rgba(19,37,33,.13)';
    ctx.beginPath();
    ctx.ellipse(12, 102, 104, 24, 0, 0, Math.PI * 2);
    ctx.fill();
    if (label === 'ceramic') {
      const glaze = ctx.createLinearGradient(-80, -100, 100, 80);
      glaze.addColorStop(0, '#88afba');
      glaze.addColorStop(0.4, '#396b82');
      glaze.addColorStop(1, '#17485d');
      ctx.fillStyle = glaze;
      ctx.beginPath();
      ctx.roundRect(-85, -103, 170, 201, [28, 28, 62, 62]);
      ctx.fill();
      ctx.strokeStyle = '#c2d7d7';
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.ellipse(0, -97, 78, 17, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.strokeStyle = 'rgba(218,240,233,.32)';
      ctx.lineWidth = 3;
      for (let i = -50; i < 70; i += 24) {
        ctx.beginPath();
        ctx.moveTo(i, -63);
        ctx.lineTo(i - 8, 62);
        ctx.stroke();
      }
      ctx.strokeStyle = '#376479';
      ctx.lineWidth = 19;
      ctx.beginPath();
      ctx.ellipse(96, -3, 33, 49, 0.1, -1.6, 1.6);
      ctx.stroke();
    } else if (label === 'bottles') {
      const glass = ctx.createLinearGradient(-65, 0, 80, 0);
      glass.addColorStop(0, '#286e62');
      glass.addColorStop(0.3, '#639c83');
      glass.addColorStop(1, '#194e4b');
      ctx.fillStyle = glass;
      ctx.beginPath();
      ctx.moveTo(-32, -122);
      ctx.lineTo(32, -122);
      ctx.lineTo(32, -58);
      ctx.bezierCurveTo(33, -32, 72, -30, 72, 0);
      ctx.lineTo(72, 94);
      ctx.quadraticCurveTo(0, 113, -72, 94);
      ctx.lineTo(-72, 0);
      ctx.bezierCurveTo(-72, -30, -33, -32, -32, -58);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = '#c1a579';
      ctx.fillRect(-35, -138, 70, 28);
      ctx.fillStyle = '#f0e8d6';
      ctx.beginPath();
      ctx.roundRect(-56, 1, 112, 64, 3);
      ctx.fill();
      ctx.fillStyle = '#335a4f';
      ctx.font = 'bold 13px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('FIELD / 07', 0, 27);
      ctx.font = '9px sans-serif';
      ctx.fillText('BOTANICAL COLLECTION', 0, 44);
      ctx.fillStyle = 'rgba(255,255,255,.18)';
      ctx.fillRect(-51, -32, 10, 24);
    } else {
      const metal = ctx.createLinearGradient(-110, -80, 100, 90);
      metal.addColorStop(0, '#f2bd83');
      metal.addColorStop(0.4, '#c77e4f');
      metal.addColorStop(0.7, '#9b553b');
      metal.addColorStop(1, '#e2a46e');
      ctx.fillStyle = metal;
      ctx.beginPath();
      ctx.roundRect(-97, -86, 194, 179, 18);
      ctx.fill();
      ctx.strokeStyle = '#f4c693';
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.fillStyle = '#ad6743';
      ctx.beginPath();
      ctx.ellipse(0, -78, 88, 15, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#deb18a';
      ctx.beginPath();
      ctx.roundRect(-26, -108, 52, 20, 5);
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,215,174,.4)';
      ctx.lineWidth = 1;
      for (let i = -75; i < 90; i += 15) {
        ctx.beginPath();
        ctx.moveTo(i, -51);
        ctx.lineTo(i, 67);
        ctx.stroke();
      }
    }
    ctx.restore();
    ctx.fillStyle = '#40524c';
    ctx.font = '11px monospace';
    ctx.textAlign = 'left';
    ctx.fillText('SPLITLENS   /   MATERIAL STUDY', 28, 30);
    ctx.fillText(`${label.toUpperCase()}   ${String(variant + 1).padStart(2, '0')}`, 28, 355);
    ctx.fillStyle = '#9b7252';
    ctx.beginPath();
    ctx.arc(469, 349, 7, 0, Math.PI * 2);
    ctx.fill();
    if (mode === 'near') {
      ctx.fillStyle = '#345b59';
      ctx.fillRect(455, 335, 22, 6);
    }
    if (mode === 'dark') {
      ctx.fillStyle = 'rgba(0,0,0,.94)';
      ctx.fillRect(0, 0, 512, 384);
    }
    if (mode === 'bright') {
      ctx.fillStyle = 'rgba(255,255,255,.96)';
      ctx.fillRect(0, 0, 512, 384);
    }
    if (mode === 'blur') {
      const copy = document.createElement('canvas');
      copy.width = canvas.width;
      copy.height = canvas.height;
      copy.getContext('2d')!.drawImage(canvas, 0, 0);
      ctx.resetTransform();
      ctx.filter = 'blur(18px)';
      ctx.drawImage(copy, -20, -20, canvas.width + 40, canvas.height + 40);
      ctx.filter = 'none';
    }
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (value) => (value ? resolve(value) : reject(new Error('Could not create demo image.'))),
        'image/png',
      ),
    );
    const file = new File([blob], path.split('/').at(-1)!, { type: 'image/png' });
    const split = path.split('/')[0] as Split;
    const input: InputImage = { id: `demo-${inputs.length}`, path, file, split };
    inputs.push(input);
    return input;
  };
  for (const label of classes) {
    for (let i = 0; i < 7; i++)
      await create(label, i, `${i < 5 ? 'train' : 'validation'}/${label}/sample-${i + 1}.png`);
  }
  const ceramic = inputs[0];
  inputs.push({
    id: `demo-${inputs.length}`,
    path: 'validation/ceramic/copy-from-train.png',
    file: new File([ceramic.file], 'copy-from-train.png', { type: 'image/png' }),
    split: 'validation',
  });
  const bottle = inputs[8];
  inputs.push({
    id: `demo-${inputs.length}`,
    path: 'train/bottles/duplicate-shot.png',
    file: new File([bottle.file], 'duplicate-shot.png', { type: 'image/png' }),
    split: 'train',
  });
  await create('copper', 1, 'test/copper/retouched-shot.png', 'near');
  await create('ceramic', 4, 'train/ceramic/out-of-focus.png', 'blur');
  await create('bottles', 2, 'train/bottles/underexposed.png', 'dark');
  await create('copper', 3, 'validation/copper/overexposed.png', 'bright');
  await create('ceramic', 2, 'test/ceramic/thumbnail-only.png', 'normal', 96);
  inputs.push({
    id: `demo-${inputs.length}`,
    path: 'train/copper/interrupted-upload.png',
    file: new File(['An intentionally interrupted image upload.'], 'interrupted-upload.png', {
      type: 'image/png',
    }),
    split: 'train',
  });
  return inputs;
}
