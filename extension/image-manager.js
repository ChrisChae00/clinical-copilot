// ImageManager
// Handles image attachments for the chat UI.

(function () {
  'use strict';

  class ImageManager {
    constructor({ attachButton, fileInput, pasteTarget, previewList, onError } = {}) {
      if (!attachButton) throw new Error('Image attach button is required.');
      if (!fileInput) throw new Error('Image file input is required.');
      if (!pasteTarget) throw new Error('Image paste target is required.');
      if (!previewList) throw new Error('Image preview list is required.');

      this.attachButton = attachButton;
      this.fileInput = fileInput;
      this.pasteTarget = pasteTarget;
      this.previewList = previewList;
      this.onError = onError || ((err) => console.error(err));
      this.images = [];
      this.disabled = false;

      this.bindEvents();
      this.render();
    }

    bindEvents() {
      this.attachButton.addEventListener('click', () => {
        if (!this.disabled) this.fileInput.click();
      });

      this.fileInput.addEventListener('change', async () => {
        await this.addFiles(Array.from(this.fileInput.files || []));
        this.fileInput.value = '';
      });

      this.pasteTarget.addEventListener('paste', async (event) => {
        const files = this.getImageFilesFromPaste(event);
        if (!files.length) return;

        event.preventDefault();
        await this.addFiles(files);
      });
    }

    get count() {
      return this.images.length;
    }

    getImages() {
      return this.images.slice();
    }

    getImagesBase64() {
      return this.images.map((image) => image.b64);
    }

    clear() {
      this.images = [];
      this.fileInput.value = '';
      this.render();
    }

    setDisabled(disabled) {
      this.disabled = Boolean(disabled);
      this.attachButton.disabled = this.disabled;
      this.fileInput.disabled = this.disabled;
      this.render();
    }

    async addFiles(files) {
      for (const file of files) {
        if (!file?.type?.startsWith('image/')) continue;

        try {
          this.images.push(await this.readImageFile(file));
        } catch (err) {
          this.onError(err);
        }
      }

      this.render();
    }

    getImageFilesFromPaste(event) {
      return Array.from(event.clipboardData?.items || [])
        .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
        .map((item) => item.getAsFile())
        .filter(Boolean);
    }

    readImageFile(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = () => {
          const dataUrl = String(reader.result || '');
          const commaIndex = dataUrl.indexOf(',');

          resolve({
            id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
            name: file.name || 'pasted-image',
            type: file.type,
            dataUrl,
            b64: commaIndex >= 0 ? dataUrl.slice(commaIndex + 1) : dataUrl,
          });
        };

        reader.onerror = () => {
          reject(new Error(`Could not read ${file.name || 'image'}.`));
        };

        reader.readAsDataURL(file);
      });
    }

    render() {
      this.previewList.textContent = '';
      this.previewList.classList.toggle('hidden', this.images.length === 0);

      this.images.forEach((image) => {
        this.previewList.appendChild(this.createPreview(image));
      });
    }

    createPreview(image) {
      const item = document.createElement('div');
      item.className = 'image-preview';

      const img = document.createElement('img');
      img.src = image.dataUrl;
      img.alt = image.name;
      item.appendChild(img);

      const removeBtn = document.createElement('button');
      removeBtn.className = 'image-remove-btn';
      removeBtn.type = 'button';
      removeBtn.textContent = '×';
      removeBtn.disabled = this.disabled;
      removeBtn.setAttribute('aria-label', `Remove ${image.name}`);
      removeBtn.addEventListener('click', () => this.remove(image.id));
      item.appendChild(removeBtn);

      return item;
    }

    remove(imageId) {
      if (this.disabled) return;

      this.images = this.images.filter((image) => image.id !== imageId);
      this.render();
    }
  }

  window.ImageManager = ImageManager;
})();
