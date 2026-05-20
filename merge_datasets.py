import shutil
import os
import yaml

def merge_datasets(src1, src2, dest):
    os.makedirs(dest, exist_ok=True)
    
    # Yeni data.yaml içeriği
    abs_dest = os.path.abspath(dest)
    new_data = {
        'path': abs_dest,
        'train': 'train/images',
        'val': 'valid/images',
        'test': 'test/images',
        'names': {0: 'box', 1: 'billboard'},
        'nc': 2
    }
    
    splits = ['train', 'valid', 'test']
    
    for split in splits:
        img_dest = os.path.join(dest, split, 'images')
        lbl_dest = os.path.join(dest, split, 'labels')
        os.makedirs(img_dest, exist_ok=True)
        os.makedirs(lbl_dest, exist_ok=True)
        
        # Dataset 1 (Box) - Class 0
        src1_split = split if split != 'valid' else 'valid' # boxes uses 'valid'
        s1_img_dir = os.path.join(src1, src1_split, 'images')
        s1_lbl_dir = os.path.join(src1, src1_split, 'labels')
        
        if os.path.exists(s1_img_dir):
            for f in os.listdir(s1_img_dir):
                shutil.copy(os.path.join(s1_img_dir, f), os.path.join(img_dest, 'box_' + f))
        
        if os.path.exists(s1_lbl_dir):
            for f in os.listdir(s1_lbl_dir):
                # Class index'i 0 kalsın (zaten 0 idi)
                shutil.copy(os.path.join(s1_lbl_dir, f), os.path.join(lbl_dest, 'box_' + f))

        # Dataset 2 (Billboard) - Class 1
        s2_img_dir = os.path.join(src2, split, 'images')
        s2_lbl_dir = os.path.join(src2, split, 'labels')
        
        if os.path.exists(s2_img_dir):
            for f in os.listdir(s2_img_dir):
                shutil.copy(os.path.join(s2_img_dir, f), os.path.join(img_dest, 'bill_' + f))
        
        if os.path.exists(s2_lbl_dir):
            for f in os.listdir(s2_lbl_dir):
                # Class index'i 1 yap ve box formatını polygona çevir
                with open(os.path.join(s2_lbl_dir, f), 'r') as fr:
                    lines = fr.readlines()
                with open(os.path.join(lbl_dest, 'bill_' + f), 'w') as fw:
                    for line in lines:
                        parts = line.split()
                        if not parts: continue
                        
                        if len(parts) == 5:
                            # Box format: class cx cy w h
                            cls_id, cx, cy, w, h = map(float, parts)
                            x1, y1 = cx - w/2, cy - h/2
                            x2, y2 = cx + w/2, cy - h/2
                            x3, y3 = cx + w/2, cy + h/2
                            x4, y4 = cx - w/2, cy + h/2
                            # Polygon format: class x1 y1 x2 y2 x3 y3 x4 y4
                            fw.write(f"1 {x1} {y1} {x2} {y2} {x3} {y3} {x4} {y4}\n")
                        else:
                            # Zaten polygon formatında (veya geçersiz)
                            parts[0] = '1'
                            fw.write(' '.join(parts) + '\n')

    with open(os.path.join(dest, 'data.yaml'), 'w') as f:
        yaml.dump(new_data, f)

if __name__ == "__main__":
    merge_datasets('boxes-segmentation-2-1', 'BillBoard-3', 'training_data/datasets/combined_data')
    print("Veri setleri başarıyla birleştirildi.")
