using System;
using System.IO;
using System.Net.Sockets;
using System.Threading;
using UnityEngine;

public class CarlaTcpReceiver : MonoBehaviour
{
    [Header("Network")]
    public string Host = "127.0.0.1";
    public int Port = 5001;

    [Header("Target")]
    public Renderer TargetRenderer; // das Quad/Mesh, dessen Material die Textur bekommt
    public bool UseLinearColorSpace = false;

    private Thread _thread;
    private volatile bool _running;
    private Texture2D _tex;
    private byte[] _lenBuf = new byte[4];
    private byte[] _imgBuf = new byte[8 * 1024 * 1024]; // 8 MB Puffer
    private readonly object _lock = new object();
    private byte[] _latestJpeg;

    void Start()
    {
        // Texture initialisieren (Dummy)
        _tex = new Texture2D(2, 2, TextureFormat.RGB24, false, UseLinearColorSpace);
        if (TargetRenderer != null)
        {
            TargetRenderer.material = new Material(Shader.Find("Unlit/Texture"));
            TargetRenderer.material.mainTexture = _tex;
        }

        _running = true;
        _thread = new Thread(ReceiveLoop) { IsBackground = true };
        _thread.Start();
    }

    void OnDestroy()
    {
        _running = false;
        _thread?.Join(500);
    }

    void Update()
    {
        byte[] jpeg = null;
        lock (_lock)
        {
            if (_latestJpeg != null)
            {
                jpeg = _latestJpeg;
                _latestJpeg = null; // einmal nutzen
            }
        }

        if (jpeg != null)
        {
            try
            {
                if (_tex.LoadImage(jpeg, markNonReadable: false))
                {
                    // Textur aktualisiert – Material bekommt es automatisch
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning("JPEG decode failed: " + e.Message);
            }
        }
    }

    private void ReceiveLoop()
    {
        try
        {
            using (var client = new TcpClient())
            {
                client.NoDelay = true;
                client.Connect(Host, Port);

                using (var stream = client.GetStream())
                {
                    while (_running)
                    {
                        // 4 Byte Länge lesen (big-endian / network order)
                        if (!ReadExactly(stream, _lenBuf, 4)) break;
                        int len = ((int)_lenBuf[0] << 24) | ((int)_lenBuf[1] << 16) | ((int)_lenBuf[2] << 8) | _lenBuf[3];

                        if (len <= 0 || len > _imgBuf.Length) break;

                        if (!ReadExactly(stream, _imgBuf, len)) break;

                        var jpeg = new byte[len];
                        Buffer.BlockCopy(_imgBuf, 0, jpeg, 0, len);

                        lock (_lock)
                        {
                            _latestJpeg = jpeg;
                        }
                    }
                }
            }
        }
        catch (Exception e)
        {
            Debug.LogError("ReceiveLoop Exception: " + e.Message);
        }
    }

    private bool ReadExactly(NetworkStream stream, byte[] buffer, int size)
    {
        int offset = 0;
        while (offset < size)
        {
            int read = stream.Read(buffer, offset, size - offset);
            if (read <= 0) return false;
            offset += read;
        }
        return true;
    }
}

