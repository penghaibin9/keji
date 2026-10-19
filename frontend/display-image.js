// 展示图片（封面、头像、场地照片）：选填，PNG 或 JPG，不超过 5MB；与证明材料分开，仅用于展示。
export const IMAGE_ACCEPT = '.png,.jpg,.jpeg,image/png,image/jpeg';
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export function imageField(c, name, label, hint) {
  return c.field(name, label, 'file', '', {required: false, accept: IMAGE_ACCEPT, full: true,
    hint: hint || '选填，PNG 或 JPG，不超过 5MB；仅用于展示，不能代替证明材料。'});
}

// 从表单取出所选图片；没选返回 null，格式或大小不合要求时直接报错，避免保存后才发现。
export function takeImage(values, name) {
  const file = values[name];
  delete values[name];
  if (!file || typeof file !== 'object' || !file.size) return null;
  if (!/\.(png|jpe?g)$/i.test(file.name || '')) throw Error('展示图片只接收 PNG、JPG 格式');
  if (file.size > MAX_IMAGE_BYTES) throw Error('展示图片不能超过 5MB');
  return file;
}

// 记录保存成功后再上传图片。上传失败不让表单报错（记录已保存，重复提交会产生重复记录），
// 改为提示“可在详情里重试”。
export async function saveImageAfter(c, target, result, file, purpose = 'cover') {
  if (!file || !result?.item?.id) return result;
  try {
    const form = new FormData();
    form.append('file', file);
    form.append('purpose', purpose);
    form.append('expected_version', String(result.item.version));
    await c.api('/social/images/' + target + '/' + result.item.id, {method: 'POST', body: form});
  } catch (err) {
    c.toast('记录已保存，但图片上传失败：' + err.message + '。可打开详情后点“上传封面”重试。', true);
  }
  return result;
}

// 详情页里的“上传 / 更换封面”按钮；参数格式与列表里的 training-image 一致。
export function coverButton(c, target, item, label = '封面') {
  return c.act((item.data?.cover_id ? '更换' : '上传') + label, 'training-image', [target, item.id, 'cover', item.version].join('|'));
}
